# 동영상 데모
https://www.youtube.com/watch?v=h6pufhmljZs

# 전수조사 AI 감사 Agent (kpmg-portfolio)

원장(CSV)을 업로드하면 표준화된 형태로 매핑하고, 데이터 시각화 분석과 다양한 **부정징후(Fraud Indicator) 탐지 알고리즘**을 실행해 문제 있는 분개를 즉시 추출해주는 AI 감사 보조 도구입니다.

## 아키텍처

```
frontend/   Next.js 16 (App Router) + Tailwind v4 + AG Grid + Recharts + Zustand
backend/    FastAPI + DuckDB + pandas (부정징후 탐지 알고리즘 포함)
```

- 프론트엔드는 `NEXT_PUBLIC_API_URL` (기본값 `http://localhost:8000`)로 백엔드와 통신합니다.
- 백엔드는 업로드된 CSV를 `backend/temp_files/`에 저장하고, DuckDB로 쿼리하거나 pandas 기반 알고리즘으로 분석합니다.
- 자연어 질의(`/api/chat`)는 `OPENAI_API_KEY`가 설정된 경우 LLM이 SQL을 생성하고, 키가 없으면 단순 키워드 검색으로 자동 대체됩니다.

## 실행 방법

### 1. 백엔드 (FastAPI)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 필요 시 OPENAI_API_KEY 등 설정
uvicorn main:app --reload --port 8000
```

### 2. 프론트엔드 (Next.js)

```bash
cd frontend
npm install
cp .env.example .env.local   # 필요 시 NEXT_PUBLIC_API_URL 수정
npm run dev
```

브라우저에서 `http://localhost:3000` 접속 후, 원장 CSV 업로드 → 컬럼 매핑 → 좌측 사이드바에서 부정징후 알고리즘 클릭 순으로 사용합니다. 

## 웹 배포 (추천: Vercel + Render)

프론트(Next.js)는 **Vercel**, 백엔드(FastAPI)는 **Render**에 올리는 구성을 기준으로 합니다.

### 1) 백엔드 — Render

1. [Render](https://render.com)에서 New → Blueprint (또는 Web Service)
2. 이 GitHub 저장소 연결, 브랜치 `main`
3. Blueprint를 쓰면 루트 `render.yaml`이 자동 적용됩니다. 수동이면:
   - Root Directory: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment:
   - `FRONTEND_ORIGIN` = Vercel 프론트 URL (예: `https://xxx.vercel.app`) — 여러 개면 쉼표 구분
   - `OPENAI_API_KEY` = (선택) AI SQL 질의용
   - `OPENAI_MODEL` = `gpt-4o-mini` (선택)
5. 배포 후 Health: `https://<backend>.onrender.com/api/health`


### 2) 프론트 — Vercel

1. [Vercel](https://vercel.com)에서 저장소 Import
2. Root Directory: `frontend`
3. Framework Preset: Next.js
4. Environment Variable:
   - `NEXT_PUBLIC_API_URL` = Render 백엔드 URL (예: `https://xxx.onrender.com`) — **끝에 `/` 없이**
5. Deploy

### 3) CORS 연결

프론트 URL이 확정되면 Render의 `FRONTEND_ORIGIN`을 그 주소로 맞춘 뒤 백엔드를 Redeploy 하세요.  
로컬과 같이 쓰려면 예: `https://xxx.vercel.app,http://localhost:3000`

## 주요 기능

1. **원장 업로드 & 컬럼 매핑** — 어떤 CSV 스키마든 전표번호/전기일자/계정과목/거래처/차변/대변/적요 표준 필드로 매핑. 전표번호 열이 없으면 자동으로 `_row_id`가 생성되어 매핑에 사용할 수 있습니다.
2. **데이터 시각화 분석** — 원장을 로드하면 항상 월별 거래 추이, 상위 거래처 발생액, 계정과목별 발생액 차트가 표시됩니다. AI 채팅으로 원하는 축을 지정해 커스텀 차트도 생성할 수 있습니다.
3. **부정징후 탐지 알고리즘 (좌측 사이드바)** — 클릭 한 번으로 표준화된 원장 전체에 대해 즉시 검사를 수행하고, 플래그된 분개를 그리드에서 빨간색으로 강조하거나 플래그된 항목만 필터링해서 볼 수 있습니다.
   - 금액 패턴: 라운드 넘버 테스트, 승인한도 회피 탐지
   - 통계적 이상: 벤포드 법칙 위반 탐지, 계정별 통계적 이상치(Z-score), 계정별 월간 급증 탐지
   - 시점 분석: 주말/비영업일 전기 탐지, 월말 집중 전기 탐지
   - 텍스트/키워드: 특수관계자·고위험 키워드 탐지
   - 전표 무결성: 중복 지급 의심 탐지, 전표번호 결번 탐지
4. **AI 원장 질의 챗봇** — 자연어로 원장을 질의/필터링. LLM API 키가 없어도 키워드 검색으로 기본 동작합니다.

## 부정징후 알고리즘 추가하기

새 알고리즘은 `backend/fraud_algorithms.py`에 `run(df: pd.DataFrame) -> FraudResult` 형태의 함수를 추가하고, `ALGORITHMS` 리스트에 `AlgorithmSpec`으로 등록하면 프론트엔드 사이드바에 자동으로 노출됩니다 (별도의 프론트엔드 수정 불필요).
