"""
AI 감사 Agent 백엔드 (FastAPI + DuckDB + pandas)
=================================================
- /api/upload         : CSV 원장 업로드, 컬럼 목록 반환
- /api/query-test      : 회계사가 지정한 컬럼 매핑(SQL)으로 표준 원장 생성
- /api/chat            : 자연어 질의 -> (LLM 사용 가능 시) SQL 변환 -> 결과/차트
- /api/fraud-algorithms: 사용 가능한 부정징후 탐지 알고리즘 목록
- /api/fraud-check     : 특정 알고리즘을 표준 원장에 실행하여 의심 분개 반환
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import duckdb
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fraud_algorithms import ALGORITHM_MAP, ALGORITHMS

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp_files"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Audit Agent Backend")

_allowed_origins = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------
def _safe_file_path(file_name: str) -> Path:
    name = Path(file_name).name  # 경로 조작 방지
    path = TEMP_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {name}")
    return path


def _load_raw_df(file_name: str) -> pd.DataFrame:
    path = _safe_file_path(file_name)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _to_json_records(df: pd.DataFrame) -> str:
    clean = df.replace({np.nan: None, pd.NA: None})
    records: list[dict[str, Any]] = clean.to_dict(orient="records")
    return json.dumps(records, default=str, ensure_ascii=False)


class ColumnMapping(BaseModel):
    doc_num: str
    date: str
    account_code: str
    vendor: str
    debit_amt: str
    credit_amt: str
    desc: str


def _standardize(raw: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    missing = [col for col in mapping.dict().values() if col not in raw.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"매핑된 컬럼이 CSV에 없습니다: {missing}")

    std = pd.DataFrame(
        {
            "std_doc_num": raw[mapping.doc_num],
            "std_date": raw[mapping.date],
            "std_account_code": raw[mapping.account_code],
            "std_vendor": raw[mapping.vendor],
            "std_debit_amt": pd.to_numeric(
                raw[mapping.debit_amt].astype(str).str.replace(",", "", regex=False), errors="coerce"
            ).fillna(0),
            "std_credit_amt": pd.to_numeric(
                raw[mapping.credit_amt].astype(str).str.replace(",", "", regex=False), errors="coerce"
            ).fillna(0),
            "std_desc": raw[mapping.desc],
        }
    )
    return std


# ---------------------------------------------------------------------------
# /api/upload
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_ledger(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다.")

    dest_path = TEMP_DIR / Path(file.filename).name
    content = await file.read()
    dest_path.write_bytes(content)

    try:
        df = pd.read_csv(dest_path, dtype=str, keep_default_na=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"CSV 파싱 실패: {exc}") from exc

    # 원본에 고유 전표번호 열이 없는 경우를 대비해 자동 생성 행 ID를 추가한다.
    if "_row_id" not in df.columns:
        df.insert(0, "_row_id", range(1, len(df) + 1))
        df.to_csv(dest_path, index=False)

    return {"file_name": dest_path.name, "columns": list(df.columns), "row_count": len(df)}


# ---------------------------------------------------------------------------
# /api/query-test  (매핑 모달에서 호출: DuckDB SQL 실행)
# ---------------------------------------------------------------------------
class QueryTestRequest(BaseModel):
    file_name: str
    query_string: str


@app.post("/api/query-test")
def query_test(req: QueryTestRequest):
    path = _safe_file_path(req.file_name)

    # 프론트엔드는 항상 "FROM ledger" 형태로 쿼리를 보낸다. 실제 CSV를 뷰로 등록한다.
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(
            f"CREATE VIEW ledger AS SELECT * FROM read_csv_auto('{path.as_posix()}', ALL_VARCHAR=TRUE)"
        )
        result_df = con.execute(req.query_string).fetchdf()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"쿼리 실행 실패: {exc}") from exc
    finally:
        con.close()

    for col in ("std_debit_amt", "std_credit_amt"):
        if col in result_df.columns:
            result_df[col] = pd.to_numeric(result_df[col], errors="coerce").fillna(0)

    return {"success": True, "data": _to_json_records(result_df)}


# ---------------------------------------------------------------------------
# /api/fraud-algorithms
# ---------------------------------------------------------------------------
@app.get("/api/fraud-algorithms")
def list_fraud_algorithms():
    return {
        "algorithms": [
            {
                "id": spec.id,
                "name": spec.name,
                "category": spec.category,
                "description": spec.description,
                "risk_level": spec.risk_level,
            }
            for spec in ALGORITHMS
        ]
    }


# ---------------------------------------------------------------------------
# /api/fraud-check
# ---------------------------------------------------------------------------
class FraudCheckRequest(BaseModel):
    file_name: str
    mapping: ColumnMapping
    algorithm: str


@app.post("/api/fraud-check")
def fraud_check(req: FraudCheckRequest):
    spec = ALGORITHM_MAP.get(req.algorithm)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"알 수 없는 알고리즘입니다: {req.algorithm}")

    raw = _load_raw_df(req.file_name)
    std_df = _standardize(raw, req.mapping)

    try:
        result = spec.fn(std_df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"알고리즘 실행 중 오류: {exc}") from exc

    return {
        "success": result.success,
        "algorithm": spec.id,
        "algorithm_name": spec.name,
        "explanation": result.explanation,
        "flagged_count": len(result.flagged),
        "total_count": len(std_df),
        "stats": result.stats,
        "data": _to_json_records(result.flagged),
    }


# ---------------------------------------------------------------------------
# /api/chat  (자연어 질의 -> SQL, LLM 사용 가능 시 / 없으면 키워드 폴백)
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    file_name: str
    message: str
    history: list[ChatMessage] = []
    mapping: ColumnMapping


_STD_COLUMNS = [
    "std_doc_num",
    "std_date",
    "std_account_code",
    "std_vendor",
    "std_debit_amt",
    "std_credit_amt",
    "std_desc",
]


def _llm_generate_sql(message: str, history: list[ChatMessage]) -> Optional[dict]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    system_prompt = (
        "You are an accounting audit assistant. The user's ledger is available as a DuckDB "
        "table named std_ledger with columns: std_doc_num, std_date (text date), "
        "std_account_code, std_vendor, std_debit_amt (double), std_credit_amt (double), "
        "std_desc (text). Given the user's Korean request, respond ONLY with strict JSON "
        '(no markdown) with keys: "sql" (a single SELECT statement against std_ledger), '
        '"explanation" (Korean, 1-2 sentences), "requires_chart" (bool), '
        '"chart_x" (one of the std_ columns or null), "chart_y" (one of std_debit_amt/'
        'std_credit_amt or null), "chart_type" ("bar" or null).'
    )
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:
        messages.append({"role": h.role if h.role in ("user", "assistant") else "user", "content": h.content})
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception:  # noqa: BLE001
        return None


def _fallback_keyword_search(message: str, std_df: pd.DataFrame) -> dict:
    stopwords = {"해줘", "뽑아줘", "보여줘", "그려줘", "다시", "이걸", "관련", "내역", "거래처를", "거래처의", "차트로"}
    tokens = [t for t in re.split(r"\s+", message.strip()) if len(t) >= 2 and t not in stopwords]

    if not tokens:
        return {"matched": std_df.iloc[0:0], "explanation": "질의에서 검색 키워드를 찾지 못했습니다. (LLM 미설정: 단순 키워드 검색 모드)"}

    pattern = "|".join(re.escape(t) for t in tokens)
    mask = (
        std_df["std_desc"].astype(str).str.contains(pattern, regex=True, na=False)
        | std_df["std_vendor"].astype(str).str.contains(pattern, regex=True, na=False)
        | std_df["std_account_code"].astype(str).str.contains(pattern, regex=True, na=False)
    )
    matched = std_df[mask]
    explanation = (
        f"(LLM API 키가 설정되지 않아 단순 키워드 검색으로 대체되었습니다) "
        f"'{', '.join(tokens)}' 관련 {len(matched):,}건을 찾았습니다."
    )
    return {"matched": matched, "explanation": explanation}


@app.post("/api/chat")
def chat(req: ChatRequest):
    raw = _load_raw_df(req.file_name)
    std_df = _standardize(raw, req.mapping)

    llm_result = _llm_generate_sql(req.message, req.history)

    if llm_result and llm_result.get("sql"):
        con = duckdb.connect(database=":memory:")
        try:
            con.register("std_ledger", std_df)
            result_df = con.execute(llm_result["sql"]).fetchdf()
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "explanation": f"SQL 실행에 실패했습니다: {exc}"}
        finally:
            con.close()

        return {
            "success": True,
            "explanation": llm_result.get("explanation", "요청하신 데이터를 조회했습니다."),
            "data": _to_json_records(result_df),
            "requires_chart": bool(llm_result.get("requires_chart")),
            "chart_x": llm_result.get("chart_x"),
            "chart_y": llm_result.get("chart_y"),
            "chart_type": llm_result.get("chart_type"),
        }

    fallback = _fallback_keyword_search(req.message, std_df)
    return {
        "success": True,
        "explanation": fallback["explanation"],
        "data": _to_json_records(fallback["matched"]),
        "requires_chart": False,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
