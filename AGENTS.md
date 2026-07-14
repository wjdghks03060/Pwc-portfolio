# AGENTS.md

## Product overview

Korean **매출 감사 AI Agent** — upload a general-ledger CSV, map columns, inspect rows in AG Grid, and chat with an audit agent that filters DuckDB data / builds charts.

| Service | Command | Port |
|---------|---------|------|
| Frontend (Next.js) | `cd frontend && npm run dev` | 3000 |
| Backend (FastAPI + DuckDB) | `cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000` | 8000 |

Sample ledger: `backend/temp_files/fdd_sample_general_ledger_300.csv`.

## Cursor Cloud specific instructions

- Frontend install needs `npm install --legacy-peer-deps` because `@tremor/react` declares a React 18 peer while the app uses React 19 (`@tremor/react` is unused in source; charts are custom).
- Backend was missing from the repo (only the sample CSV existed). A minimal FastAPI app in `backend/main.py` implements the three endpoints the frontend hardcodes (`/api/upload`, `/api/query-test`, `/api/chat`). Chat uses OpenAI when `OPENAI_API_KEY` is set; otherwise a vendor/account/month heuristic falls back so local demos work without secrets.
- Backend deps live in `backend/venv` (gitignored). Activate that venv before running uvicorn.
- Lint (`cd frontend && npm run lint`) currently reports pre-existing `@typescript-eslint/no-explicit-any` / unused-var issues in `page.tsx`, `LedgerGrid.tsx`, and `MappingModal.tsx`.
- There is no automated test suite. Smoke via: upload the sample CSV → map columns (Date→전기일자, Account_Code→전표번호, Account_Name→계정과목, Vendor→거래처, Debit/Credit, Description→적요) → ask the agent e.g. `통신비 내역 뽑아줘` or `월별 추이액 차트로 그려줘`.
- See `frontend/README.md` for stock Next.js scripts; see `frontend/AGENTS.md` for Next.js 16 agent notes.
