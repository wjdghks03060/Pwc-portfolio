"""
Minimal FastAPI + DuckDB backend for the 매출 감사 AI Agent frontend.

Endpoints expected by frontend/:
  POST /api/upload
  POST /api/query-test
  POST /api/chat
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "temp_files"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Audit AI Agent Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryTestRequest(BaseModel):
    file_name: str
    query_string: str


class ColumnMapping(BaseModel):
    doc_num: str
    date: str
    account_code: str
    vendor: str
    debit_amt: str
    credit_amt: str
    desc: str


class ChatRequest(BaseModel):
    file_name: str
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    mapping: ColumnMapping | None = None


def _file_path(file_name: str) -> Path:
    path = (UPLOAD_DIR / Path(file_name).name).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file name")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_name}")
    return path


def _connect_ledger(file_name: str) -> duckdb.DuckDBPyConnection:
    path = _file_path(file_name)
    con = duckdb.connect()
    con.execute(
        f"CREATE OR REPLACE VIEW ledger AS SELECT * FROM read_csv_auto('{path.as_posix()}', header=true)"
    )
    return con


def _rows_to_grid_json(df: pd.DataFrame) -> str:
    """Normalize dates to epoch-ms so AG Grid date filters work."""
    records = df.to_dict(orient="records")
    for row in records:
        for key, value in list(row.items()):
            if value is None or (isinstance(value, float) and pd.isna(value)):
                row[key] = None
                continue
            if key == "std_date" or "date" in key.lower():
                ts = pd.to_datetime(value, errors="coerce")
                if pd.notna(ts):
                    row[key] = int(ts.timestamp() * 1000)
    return json.dumps(records, ensure_ascii=False, default=str)


def _mapped_select_sql(mapping: ColumnMapping) -> str:
    return f"""
        SELECT
          "{mapping.date}" AS std_date,
          "{mapping.doc_num}" AS std_doc_num,
          "{mapping.account_code}" AS std_account_code,
          "{mapping.vendor}" AS std_vendor,
          CAST("{mapping.debit_amt}" AS DOUBLE) AS std_debit_amt,
          CAST("{mapping.credit_amt}" AS DOUBLE) AS std_credit_amt,
          "{mapping.desc}" AS std_desc
        FROM ledger
    """


def _heuristic_chat(message: str, mapping: ColumnMapping, file_name: str) -> dict[str, Any]:
    """Rule-based fallback when OPENAI_API_KEY is not set."""
    con = _connect_ledger(file_name)
    base_sql = _mapped_select_sql(mapping)
    where: list[str] = []
    explanation_parts: list[str] = []
    requires_chart = any(k in message for k in ("차트", "추이", "그려", "시각화"))
    chart_x = "std_date"
    chart_y = "std_debit_amt"
    chart_type = "bar"

    month_match = re.search(r"(\d{1,2})\s*월", message)
    if month_match:
        month = int(month_match.group(1))
        where.append(f"EXTRACT(MONTH FROM TRY_CAST(std_date AS TIMESTAMP)) = {month}")
        explanation_parts.append(f"{month}월 전기 분개를 필터링했습니다.")

    # Discover vendor / account tokens that actually exist in the ledger
    vendors = [
        str(v)
        for (v,) in con.execute(
            f'SELECT DISTINCT "{mapping.vendor}" FROM ledger WHERE "{mapping.vendor}" IS NOT NULL'
        ).fetchall()
    ]
    accounts = [
        str(v)
        for (v,) in con.execute(
            f'SELECT DISTINCT "{mapping.account_code}" FROM ledger WHERE "{mapping.account_code}" IS NOT NULL'
        ).fetchall()
    ]
    stop_tokens = {
        "월",
        "전기일자",
        "거래처",
        "추출",
        "뽑아",
        "그려",
        "차트",
        "추이",
        "추이액",
        "분석",
        "내역",
        "다시",
        "월별",
        "차트로",
        "이걸",
        "해주세요",
        "해주세요",
        "줘",
        "해줘",
    }
    tokens = [
        t
        for t in re.findall(r"[A-Za-z0-9가-힣]+", message)
        if len(t) >= 2 and t not in stop_tokens and not re.fullmatch(r"\d{1,2}", t)
    ]
    catalog = sorted(set(vendors + accounts), key=len, reverse=True)
    chosen: list[str] = []
    for token in tokens:
        for candidate in catalog:
            if token in candidate or candidate in token or candidate in message:
                if candidate not in chosen and not any(candidate in c or c in candidate for c in chosen):
                    chosen.append(token if token in candidate else candidate)
                break
        if len(chosen) >= 2:
            break
    for term in chosen:
        where.append(
            f"(CAST(std_vendor AS VARCHAR) LIKE '%{term}%' OR CAST(std_account_code AS VARCHAR) LIKE '%{term}%' OR CAST(std_desc AS VARCHAR) LIKE '%{term}%')"
        )
        explanation_parts.append(f"'{term}' 조건으로 필터링했습니다.")

    if requires_chart:
        explanation_parts.append("월별 추이 차트를 생성했습니다.")

    filtered = f"SELECT * FROM ({base_sql}) AS mapped"
    if where:
        filtered += " WHERE " + " AND ".join(where)

    try:
        df = con.execute(filtered).fetchdf()
    except Exception as exc:  # noqa: BLE001
        con.close()
        return {
            "success": False,
            "explanation": f"쿼리 실행 중 오류가 발생했습니다: {exc}",
            "data": "[]",
        }
    con.close()

    if not explanation_parts:
        explanation_parts.append(f"총 {len(df)}건의 분개를 반환했습니다.")
    else:
        explanation_parts.insert(0, f"조건에 맞는 분개 {len(df)}건을 추출했습니다.")

    return {
        "success": True,
        "explanation": "\n".join(explanation_parts),
        "data": _rows_to_grid_json(df),
        "requires_chart": requires_chart,
        "chart_x": chart_x,
        "chart_y": chart_y,
        "chart_type": chart_type,
    }


async def _openai_chat(req: ChatRequest) -> dict[str, Any]:
    from openai import OpenAI

    if req.mapping is None:
        raise HTTPException(status_code=400, detail="mapping is required for chat")

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    con = _connect_ledger(req.file_name)
    sample = con.execute(f"{_mapped_select_sql(req.mapping)} LIMIT 5").fetchdf()
    con.close()

    system = (
        "You are a Korean accounting audit assistant. "
        "Given a general ledger and a user request, reply with JSON only: "
        '{"sql_where": "optional SQL WHERE clause without the WHERE keyword using std_* columns", '
        '"explanation": "Korean explanation", '
        '"requires_chart": boolean, "chart_x": "std_date|std_vendor|...", '
        '"chart_y": "std_debit_amt|std_credit_amt", "chart_type": "bar"}. '
        "Columns: std_date, std_doc_num, std_account_code, std_vendor, std_debit_amt, std_credit_amt, std_desc."
    )
    user_payload = {
        "message": req.message,
        "sample_rows": json.loads(sample.to_json(orient="records", force_ascii=False)),
        "history": req.history[-6:],
    }
    completion = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    plan = json.loads(completion.choices[0].message.content or "{}")

    con = _connect_ledger(req.file_name)
    sql = f"SELECT * FROM ({_mapped_select_sql(req.mapping)}) AS mapped"
    where = (plan.get("sql_where") or "").strip()
    if where:
        sql += f" WHERE {where}"
    try:
        df = con.execute(sql).fetchdf()
        success = True
        explanation = plan.get("explanation") or f"{len(df)}건 추출"
    except Exception as exc:  # noqa: BLE001
        df = con.execute(f"SELECT * FROM ({_mapped_select_sql(req.mapping)}) AS mapped").fetchdf()
        success = False
        explanation = f"AI 쿼리 실패로 전체 데이터를 반환합니다: {exc}"
    con.close()

    return {
        "success": success,
        "explanation": explanation,
        "data": _rows_to_grid_json(df),
        "requires_chart": bool(plan.get("requires_chart")),
        "chart_x": plan.get("chart_x") or "std_date",
        "chart_y": plan.get("chart_y") or "std_debit_amt",
        "chart_type": plan.get("chart_type") or "bar",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)

    try:
        con = duckdb.connect()
        cols = [
            r[0]
            for r in con.execute(
                f"DESCRIBE SELECT * FROM read_csv_auto('{dest.as_posix()}', header=true)"
            ).fetchall()
        ]
        con.close()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"CSV parse failed: {exc}") from exc

    return {"file_name": safe_name, "columns": cols}


@app.post("/api/query-test")
async def query_test(body: QueryTestRequest) -> dict[str, Any]:
    con = _connect_ledger(body.file_name)
    try:
        df = con.execute(body.query_string).fetchdf()
    except Exception as exc:  # noqa: BLE001
        con.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    con.close()
    return {"data": _rows_to_grid_json(df)}


@app.post("/api/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    if body.mapping is None:
        raise HTTPException(status_code=400, detail="mapping is required")
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return await _openai_chat(body)
        except Exception as exc:  # noqa: BLE001
            # Fall back to heuristics so local demo remains usable
            result = _heuristic_chat(body.message, body.mapping, body.file_name)
            result["explanation"] = (
                f"(OpenAI 호출 실패 → 규칙 기반 폴백) {exc}\n\n" + result["explanation"]
            )
            return result
    return _heuristic_chat(body.message, body.mapping, body.file_name)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
