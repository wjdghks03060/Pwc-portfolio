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
        "table named std_ledger with columns: std_doc_num, std_date (TEXT 'YYYY-MM-DD'), "
        "std_account_code, std_vendor, std_debit_amt (double), std_credit_amt (double), "
        "std_desc (text).\n"
        "Rules for SQL:\n"
        "- Return a single SELECT against std_ledger only.\n"
        "- std_date is TEXT, NOT a DATE type. For a month like June 2023 use "
        "std_date >= '2023-06-01' AND std_date < '2023-07-01' (or LIKE '2023-06%'). "
        "Do NOT use month()/year()/strftime on std_date unless you CAST it first.\n"
        "- For Korean vendor names, prefer std_vendor LIKE '%카카오%' over exact equality.\n"
        "- Keep all std_* columns in the SELECT list when returning journal rows.\n"
        "Respond ONLY with strict JSON (no markdown) with keys: "
        '"sql", "explanation" (Korean, 1-2 sentences, do not invent row counts), '
        '"requires_chart" (bool), "chart_x" (std_ column or null), '
        '"chart_y" (std_debit_amt/std_credit_amt or null), "chart_type" ("bar" or null).'
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


def _parse_year_month(message: str) -> tuple[Optional[str], Optional[str]]:
    """한국어 질의에서 연/월을 추출. 예: 2023년 6월 -> ('2023', '06')"""
    year = None
    month = None
    ym = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월", message)
    if ym:
        year, month = ym.group(1), f"{int(ym.group(2)):02d}"
        return year, month
    y_only = re.search(r"(20\d{2})\s*년", message)
    if y_only:
        year = y_only.group(1)
    m_only = re.search(r"(?<!\d)(\d{1,2})\s*월", message)
    if m_only:
        month = f"{int(m_only.group(1)):02d}"
    return year, month


def _fallback_keyword_search(message: str, std_df: pd.DataFrame) -> dict:
    stopwords = {
        "해줘", "뽑아줘", "보여줘", "그려줘", "다시", "이걸", "관련", "내역",
        "거래처를", "거래처의", "차트로", "추출해줘", "거래만", "분개", "원장",
    }
    tokens = [t for t in re.split(r"\s+", message.strip()) if len(t) >= 2 and t not in stopwords]
    # '2023년', '6월' 같은 토큰은 날짜 필터로 처리하므로 텍스트 검색에서 제외
    text_tokens = [
        t for t in tokens
        if not re.fullmatch(r"20\d{2}년?", t)
        and not re.fullmatch(r"\d{1,2}월", t)
    ]

    mask = pd.Series(True, index=std_df.index)
    year, month = _parse_year_month(message)
    dates = std_df["std_date"].astype(str)
    if year and month:
        mask &= dates.str.startswith(f"{year}-{month}")
    elif year:
        mask &= dates.str.startswith(year)
    elif month:
        mask &= dates.str.contains(rf"-{month}-", regex=True, na=False)

    if text_tokens:
        pattern = "|".join(re.escape(t) for t in text_tokens)
        text_mask = (
            std_df["std_desc"].astype(str).str.contains(pattern, regex=True, na=False)
            | std_df["std_vendor"].astype(str).str.contains(pattern, regex=True, na=False)
            | std_df["std_account_code"].astype(str).str.contains(pattern, regex=True, na=False)
        )
        mask &= text_mask
    elif not (year or month):
        return {
            "matched": std_df.iloc[0:0],
            "explanation": "질의에서 검색 키워드를 찾지 못했습니다. (단순 키워드 검색 모드)",
        }

    matched = std_df[mask]
    bits = []
    if year and month:
        bits.append(f"{year}년 {int(month)}월")
    elif year:
        bits.append(f"{year}년")
    elif month:
        bits.append(f"{int(month)}월")
    if text_tokens:
        bits.append(", ".join(text_tokens))
    explanation = f"'{ ' / '.join(bits) }' 조건으로 {len(matched):,}건을 찾았습니다."
    return {"matched": matched, "explanation": explanation}


def _ensure_std_columns(result_df: pd.DataFrame, std_df: pd.DataFrame) -> pd.DataFrame:
    """집계 결과가 아닌 행 조회인데 std_ 컬럼이 빠지면 원본 스키마로 맞춘다."""
    if result_df.empty:
        return result_df
    missing = [c for c in _STD_COLUMNS if c not in result_df.columns]
    if not missing:
        return result_df
    # 집계/차트용 결과(그룹 컬럼만 있는 경우)는 그대로 둔다
    if not any(c in result_df.columns for c in _STD_COLUMNS):
        return result_df
    return result_df


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
            # SQL 실패 시 키워드 폴백으로 재시도
            fallback = _fallback_keyword_search(req.message, std_df)
            return {
                "success": True,
                "explanation": (
                    f"SQL 실행에 실패해 키워드 검색으로 대체했습니다. ({exc}) "
                    + fallback["explanation"]
                ),
                "data": _to_json_records(fallback["matched"]),
                "requires_chart": False,
                "empty": fallback["matched"].empty,
            }
        finally:
            con.close()

        result_df = _ensure_std_columns(result_df, std_df)

        # LLM SQL이 0건이면 날짜/거래처 폴백 검색으로 한 번 더 시도
        if result_df.empty:
            fallback = _fallback_keyword_search(req.message, std_df)
            if not fallback["matched"].empty:
                return {
                    "success": True,
                    "explanation": (
                        "생성 SQL 결과가 0건이라 키워드/기간 검색으로 재조회했습니다. "
                        + fallback["explanation"]
                    ),
                    "data": _to_json_records(fallback["matched"]),
                    "requires_chart": False,
                    "empty": False,
                }

        base_explanation = llm_result.get("explanation") or "요청하신 데이터를 조회했습니다."
        explanation = f"{base_explanation} (조회 결과 {len(result_df):,}건)"
        return {
            "success": True,
            "explanation": explanation,
            "data": _to_json_records(result_df),
            "requires_chart": bool(llm_result.get("requires_chart")),
            "chart_x": llm_result.get("chart_x"),
            "chart_y": llm_result.get("chart_y"),
            "chart_type": llm_result.get("chart_type"),
            "empty": result_df.empty,
        }

    fallback = _fallback_keyword_search(req.message, std_df)
    return {
        "success": True,
        "explanation": fallback["explanation"],
        "data": _to_json_records(fallback["matched"]),
        "requires_chart": False,
        "empty": fallback["matched"].empty,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
