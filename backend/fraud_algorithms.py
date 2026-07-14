"""
부정징후(Fraud Indicator) 탐지 알고리즘 모듈
================================================
표준화된 원장 DataFrame(컬럼: std_doc_num, std_date, std_account_code,
std_vendor, std_debit_amt, std_credit_amt, std_desc)을 입력으로 받아,
각 알고리즘이 의심스러운 분개(journal entry)를 추출한다.

모든 알고리즘은 동일한 시그니처를 갖는다:
    run(df: pd.DataFrame) -> FraudResult

프론트엔드의 좌측 사이드바는 ALGORITHMS 레지스트리를 그대로 렌더링하고,
탭 클릭 시 해당 id로 /api/fraud-check 를 호출한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class FraudResult:
    success: bool
    explanation: str
    flagged: pd.DataFrame
    stats: dict = field(default_factory=dict)


def _amount(df: pd.DataFrame) -> pd.Series:
    """차변/대변 중 0이 아닌 쪽을 거래금액으로 사용."""
    debit = pd.to_numeric(df.get("std_debit_amt"), errors="coerce").fillna(0)
    credit = pd.to_numeric(df.get("std_credit_amt"), errors="coerce").fillna(0)
    values = np.where(debit.abs() >= credit.abs(), debit, credit)
    return pd.Series(values, index=df.index)


def _dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df.get("std_date"), errors="coerce")


def _empty(df: pd.DataFrame) -> pd.DataFrame:
    return df.iloc[0:0]


# ---------------------------------------------------------------------------
# 1. 라운드 넘버 테스트 (Round-Number Test)
# ---------------------------------------------------------------------------
def round_number_test(df: pd.DataFrame) -> FraudResult:
    amt = _amount(df).abs()
    work = df.copy()
    work["_amt"] = amt

    is_round = (amt >= 1_000_000) & (amt % 1_000_000 == 0)
    flagged = work[is_round].sort_values("_amt", ascending=False).drop(columns="_amt")

    total = len(df)
    hit_rate = (is_round.sum() / total * 100) if total else 0
    explanation = (
        f"전체 {total:,}건 중 100만원 단위로 정확히 나뉘는 '라운드 넘버' 거래 "
        f"{is_round.sum():,}건({hit_rate:.1f}%)을 탐지했습니다. "
        "허위 또는 임의로 추정된 금액은 실제 청구서 금액과 달리 어림수로 "
        "입력되는 경향이 있어, 정상 거래 비중과 비교해 이례적으로 높은 경우 "
        "가공/추정 전기 가능성을 의심할 수 있습니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": int(is_round.sum()), "hit_rate_pct": round(hit_rate, 2)})


# ---------------------------------------------------------------------------
# 2. 벤포드 법칙(Benford's Law) 위반 탐지
# ---------------------------------------------------------------------------
_BENFORD_EXPECTED = {d: np.log10(1 + 1 / d) for d in range(1, 10)}


def benford_law_test(df: pd.DataFrame) -> FraudResult:
    amt = _amount(df).abs()
    work = df.copy()
    work["_amt"] = amt
    valid = work[work["_amt"] >= 1]

    if valid.empty:
        return FraudResult(True, "분석 가능한 금액 데이터가 없습니다.", _empty(df), {})

    first_digit = valid["_amt"].apply(lambda x: int(str(int(x))[0]))
    counts = first_digit.value_counts().sort_index()
    total = len(valid)
    actual_pct = {d: counts.get(d, 0) / total * 100 for d in range(1, 10)}
    expected_pct = {d: _BENFORD_EXPECTED[d] * 100 for d in range(1, 10)}

    # 실제 비중이 기대치보다 유의하게(5%p 이상, 그리고 기대치의 1.5배 이상) 초과하는
    # 첫자리 숫자를 '이상 자리'로 규정한다 (표본이 작을 때의 통계적 노이즈를 배제하기 위함).
    deviant_digits = [
        d for d in range(1, 10)
        if actual_pct[d] - expected_pct[d] > 5 and actual_pct[d] > expected_pct[d] * 1.5
    ]

    valid = valid.assign(_first_digit=first_digit)
    flagged = (
        valid[valid["_first_digit"].isin(deviant_digits)]
        .sort_values("_amt", ascending=False)
        .drop(columns=["_amt", "_first_digit"])
    )

    digit_table = ", ".join(
        f"{d}로 시작 실제 {actual_pct[d]:.1f}% (기대 {expected_pct[d]:.1f}%)" for d in range(1, 10)
    )
    explanation = (
        "벤포드 법칙에 따르면 자연 발생 금액의 첫째 자리 숫자는 1이 가장 많고 9가 가장 적은 "
        "로그 분포를 따릅니다. 첫째 자리 숫자 분포를 분석한 결과, "
        + (
            f"기대치보다 크게 초과 발생한 자리수({', '.join(map(str, deviant_digits))})가 있어 "
            f"인위적으로 조작되었을 가능성이 있는 {len(flagged):,}건을 탐지했습니다."
            if deviant_digits
            else "기대 분포와 뚜렷한 편차는 발견되지 않았습니다."
        )
        + f"\n[자리수별 분포] {digit_table}"
    )
    return FraudResult(
        True,
        explanation,
        flagged,
        {"deviant_digits": deviant_digits, "actual_pct": {str(k): round(v, 2) for k, v in actual_pct.items()},
         "expected_pct": {str(k): round(v, 2) for k, v in expected_pct.items()}},
    )


# ---------------------------------------------------------------------------
# 3. 주말/비영업일 전기 탐지
# ---------------------------------------------------------------------------
def weekend_posting_test(df: pd.DataFrame) -> FraudResult:
    dates = _dates(df)
    is_weekend = dates.dt.dayofweek.isin([5, 6])
    flagged = df[is_weekend.fillna(False)].copy()
    flagged["_amt"] = _amount(flagged).abs()
    flagged = flagged.sort_values("_amt", ascending=False).drop(columns="_amt")

    total = dates.notna().sum()
    explanation = (
        f"전기일자가 토요일 또는 일요일인 분개 {len(flagged):,}건을 탐지했습니다"
        f" (분석 대상 {total:,}건 중 {(len(flagged)/total*100 if total else 0):.1f}%). "
        "정상적인 업무 프로세스에서는 발생하기 어려운 비영업일 전기는 "
        "승인 절차를 우회한 임의 전기나 시스템 접근 통제 우회의 신호일 수 있습니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": len(flagged)})


# ---------------------------------------------------------------------------
# 4. 승인한도 회피(임계값 직전 금액) 탐지
# ---------------------------------------------------------------------------
_THRESHOLDS = [1_000_000, 3_000_000, 5_000_000, 10_000_000, 30_000_000, 50_000_000, 100_000_000]
_WINDOW_PCT = 0.05  # 임계값의 5% 이내로 '직전' 금액 판정


def threshold_avoidance_test(df: pd.DataFrame) -> FraudResult:
    amt = _amount(df).abs()
    work = df.copy()
    work["_amt"] = amt

    def near_threshold(value: float) -> float | None:
        for t in _THRESHOLDS:
            lower = t * (1 - _WINDOW_PCT)
            if lower <= value < t:
                return t
        return None

    work["_threshold"] = work["_amt"].apply(near_threshold)
    flagged = work[work["_threshold"].notna()].sort_values("_amt", ascending=False)
    flagged = flagged.drop(columns=["_amt", "_threshold"])

    explanation = (
        f"결재/승인 한도로 흔히 쓰이는 금액대(100만/300만/500만/1천만/3천만/5천만/1억원)의 "
        f"바로 아래(-{int(_WINDOW_PCT*100)}% 이내) 구간에서 {len(flagged):,}건의 분개를 탐지했습니다. "
        "승인 권한 초과를 피하기 위해 금액을 인위적으로 낮춰 쪼개거나 조정했을 가능성이 있는 패턴입니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": len(flagged), "thresholds": _THRESHOLDS})


# ---------------------------------------------------------------------------
# 5. 특수관계자 · 고위험 키워드 탐지
# ---------------------------------------------------------------------------
_RISK_KEYWORDS = [
    "대표이사", "대주주", "친인척", "가족", "특수관계", "개인 차량", "개인차량",
    "위로금", "공로금", "퇴임", "접대", "골프", "유학", "학자금", "해외 유학",
    "리브랜딩", "합의금", "소송", "가산세", "과태료", "잡손실", "M&A", "인수합병",
    "법인카드", "휴양", "리조트", "밸류에이션", "자문료", "컨설팅",
]
_RISK_PATTERN = re.compile("|".join(re.escape(k) for k in _RISK_KEYWORDS))


def related_party_keyword_test(df: pd.DataFrame) -> FraudResult:
    desc = df.get("std_desc", pd.Series(dtype=str)).fillna("").astype(str)
    matches = desc.apply(lambda s: sorted(set(_RISK_PATTERN.findall(s))))
    has_match = matches.apply(lambda m: len(m) > 0)

    work = df.copy()
    work["_matched_keywords"] = matches.apply(lambda m: ", ".join(m))
    work["_amt"] = _amount(df).abs()
    flagged = work[has_match].sort_values("_amt", ascending=False).drop(columns="_amt")

    top_keywords = (
        pd.Series([kw for row in matches[has_match] for kw in row]).value_counts().head(5)
        if has_match.any()
        else pd.Series(dtype=int)
    )
    explanation = (
        f"적요(설명)에 특수관계자·고위험 키워드가 포함된 분개 {int(has_match.sum()):,}건을 탐지했습니다. "
        + (f"가장 빈번한 키워드: {', '.join(f'{k}({v}건)' for k, v in top_keywords.items())}." if len(top_keywords) else "")
        + " 대표이사/대주주 관련 지출, 접대성 경비, 소송/합의금 등은 자금유출이나 "
        "부당이득 소지가 있는 항목으로 우선 검토가 필요합니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": int(has_match.sum()), "top_keywords": top_keywords.to_dict()})


# ---------------------------------------------------------------------------
# 6. 중복 지급 의심 탐지
# ---------------------------------------------------------------------------
def duplicate_transaction_test(df: pd.DataFrame) -> FraudResult:
    work = df.copy()
    work["_amt"] = _amount(df).abs()
    work = work[work["_amt"] > 0]

    dup_mask = work.duplicated(subset=["std_vendor", "_amt"], keep=False)
    flagged = work[dup_mask].sort_values(["std_vendor", "_amt"], ascending=[True, False]).drop(columns="_amt")

    group_count = work[dup_mask].groupby(["std_vendor", "_amt"]).ngroups if dup_mask.any() else 0
    explanation = (
        f"동일 거래처에 동일 금액이 2회 이상 반복 청구된 의심 분개 {len(flagged):,}건"
        f"({group_count:,}개 그룹)을 탐지했습니다. 동일 거래처·동일 금액의 반복 지급은 "
        "중복 결제, 허위 세금계산서를 통한 대금 재청구 등의 신호일 수 있습니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": len(flagged), "group_count": group_count})


# ---------------------------------------------------------------------------
# 7. 계정별 통계적 이상치 탐지 (Z-Score)
# ---------------------------------------------------------------------------
def statistical_outlier_test(df: pd.DataFrame) -> FraudResult:
    work = df.copy()
    work["_amt"] = _amount(df)

    def z_scores(group: pd.Series) -> pd.Series:
        std = group.std(ddof=0)
        if not std or np.isnan(std):
            return pd.Series(0, index=group.index)
        return (group - group.mean()) / std

    work["_z"] = work.groupby("std_account_code")["_amt"].transform(z_scores)
    flagged = work[work["_z"].abs() >= 3].copy()
    flagged["_absz"] = flagged["_z"].abs()
    flagged = flagged.sort_values("_absz", ascending=False)
    flagged["std_desc"] = flagged.apply(
        lambda r: f"{r['std_desc']} [Z={r['_z']:.1f}]" if pd.notna(r.get("std_desc")) else f"[Z={r['_z']:.1f}]",
        axis=1,
    )
    flagged = flagged.drop(columns=["_amt", "_z", "_absz"])

    explanation = (
        f"계정과목별 금액 분포에서 표준편차 3배(|Z-score|≥3)를 초과하는 통계적 이상치 "
        f"{len(flagged):,}건을 탐지했습니다. 같은 계정 내 다른 거래들과 금액 규모가 "
        "현저히 다른 분개는 오분류, 이상 지출, 또는 의도적 조작의 가능성을 시사합니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": len(flagged)})


# ---------------------------------------------------------------------------
# 8. 월말/연말 집중 전기 탐지 (Cut-off / Period-End Concentration)
# ---------------------------------------------------------------------------
def period_end_concentration_test(df: pd.DataFrame) -> FraudResult:
    dates = _dates(df)
    work = df.copy()
    work["_date"] = dates
    work = work[work["_date"].notna()]
    if work.empty:
        return FraudResult(True, "분석 가능한 날짜 데이터가 없습니다.", _empty(df), {})

    days_in_month = work["_date"].dt.days_in_month
    day_of_month = work["_date"].dt.day
    is_period_end = day_of_month >= (days_in_month - 2)  # 월말 3일(마지막 3일)

    flagged = work[is_period_end].copy()
    flagged["_amt"] = _amount(flagged).abs()
    flagged = flagged.sort_values("_amt", ascending=False).drop(columns=["_amt", "_date"])

    total = len(work)
    rate = len(flagged) / total * 100 if total else 0
    explanation = (
        f"매월 마지막 3영업일에 전기된 분개 {len(flagged):,}건({rate:.1f}%)을 탐지했습니다. "
        "월말/기말에 비정상적으로 몰린 전기는 매출·비용 조기/지연 인식을 통한 실적 조정"
        "(cut-off 조작) 가능성을 시사할 수 있어 기간 귀속의 정확성을 확인해야 합니다."
    )
    return FraudResult(True, explanation, flagged, {"flagged_count": len(flagged), "rate_pct": round(rate, 2)})


# ---------------------------------------------------------------------------
# 9. 전표번호 결번(공백) 탐지
# ---------------------------------------------------------------------------
def doc_num_gap_test(df: pd.DataFrame) -> FraudResult:
    numeric = pd.to_numeric(df.get("std_doc_num"), errors="coerce")
    valid = numeric.dropna()

    if valid.empty or valid.nunique() < 2:
        return FraudResult(
            True,
            "전표번호가 순차적인 숫자 형식이 아니어서 결번 분석을 수행할 수 없습니다. "
            "전표번호 매핑 열을 확인해 주세요.",
            _empty(df),
            {},
        )

    ordered = sorted(valid.unique().astype(int))
    missing: list[int] = []
    for a, b in zip(ordered, ordered[1:]):
        if b - a > 1:
            missing.extend(range(a + 1, b))

    stats = {
        "missing_count": len(missing),
        "range_start": int(ordered[0]),
        "range_end": int(ordered[-1]),
        "missing_sample": missing[:30],
    }
    # 결번 자체는 원장에 '없는' 데이터이므로, 결번 인접 전표(앞/뒤)를 참고용으로 반환한다.
    adjacent_ids = set()
    for m in missing:
        adjacent_ids.add(m - 1)
        adjacent_ids.add(m + 1)
    work = df.copy()
    work["_doc_numeric"] = numeric
    flagged = work[work["_doc_numeric"].isin(adjacent_ids)].sort_values("_doc_numeric").drop(columns="_doc_numeric")

    explanation = (
        f"전표번호 {ordered[0]}~{ordered[-1]} 구간에서 결번(누락된 번호) {len(missing):,}건을 탐지했습니다"
        + (f" (예: {', '.join(map(str, missing[:10]))}{' 등' if len(missing) > 10 else ''})." if missing else ".")
        + " 결번은 전표 삭제, 취소 후 미기록, 또는 회계 시스템 외부에서의 임의 조작 가능성을 "
        "나타낼 수 있어 결번 사유에 대한 소명이 필요합니다. 아래 표는 결번과 인접한 전표들입니다."
    )
    return FraudResult(len(missing) >= 0, explanation, flagged, stats)


# ---------------------------------------------------------------------------
# 10. 계정별 월간 급증 탐지 (Spike Detection)
# ---------------------------------------------------------------------------
def account_spike_test(df: pd.DataFrame) -> FraudResult:
    dates = _dates(df)
    work = df.copy()
    work["_date"] = dates
    work["_amt"] = _amount(df)
    work = work[work["_date"].notna()]
    if work.empty:
        return FraudResult(True, "분석 가능한 날짜 데이터가 없습니다.", _empty(df), {})

    work["_month"] = work["_date"].dt.to_period("M")
    monthly = work.groupby(["std_account_code", "_month"])["_amt"].sum().reset_index()

    spikes = []
    for account, grp in monthly.groupby("std_account_code"):
        grp = grp.sort_values("_month")
        if len(grp) < 3:
            continue
        vals = grp["_amt"].values
        for i in range(len(vals)):
            baseline = np.delete(vals, i)
            mean_baseline = baseline.mean()
            if mean_baseline == 0:
                continue
            ratio = vals[i] / mean_baseline
            if ratio >= 3 and abs(vals[i] - mean_baseline) > 0:
                spikes.append((account, grp.iloc[i]["_month"], ratio))

    spike_keys = {(a, m) for a, m, _ in spikes}
    work["_key"] = list(zip(work["std_account_code"], work["_month"]))
    flagged = work[work["_key"].isin(spike_keys)].sort_values("_amt", ascending=False)
    flagged = flagged.drop(columns=["_date", "_amt", "_month", "_key"])

    top_spikes = sorted(spikes, key=lambda x: -x[2])[:5]
    spike_desc = ", ".join(f"{a}({m} 평균 대비 {r:.1f}배)" for a, m, r in top_spikes)
    explanation = (
        f"계정과목별 월간 합계액이 해당 계정의 다른 달 평균보다 3배 이상 급증한 "
        f"이례적 구간을 {len(spike_keys):,}건 탐지했습니다"
        + (f" (예: {spike_desc})." if spike_desc else ".")
        + " 특정 월에 집중된 비용 급증은 예산 소진성 지출, 부적절한 비용 처리, "
        "또는 일시적 손실 은폐 시도와 관련될 수 있습니다."
    )
    return FraudResult(True, explanation, flagged, {"spike_count": len(spike_keys)})


@dataclass
class AlgorithmSpec:
    id: str
    name: str
    category: str
    description: str
    risk_level: str  # "상" | "중" | "하"
    fn: Callable[[pd.DataFrame], FraudResult]


ALGORITHMS: list[AlgorithmSpec] = [
    AlgorithmSpec(
        id="round_number",
        name="라운드 넘버 테스트",
        category="금액 패턴",
        description="100만원 단위로 정확히 나뉘는 어림수 거래를 탐지합니다.",
        risk_level="중",
        fn=round_number_test,
    ),
    AlgorithmSpec(
        id="benford_law",
        name="벤포드 법칙 위반 탐지",
        category="통계적 이상",
        description="금액 첫째 자리 숫자 분포가 벤포드 법칙 기대치를 벗어나는 거래를 탐지합니다.",
        risk_level="상",
        fn=benford_law_test,
    ),
    AlgorithmSpec(
        id="weekend_posting",
        name="주말/비영업일 전기 탐지",
        category="시점 분석",
        description="토요일·일요일에 전기된 분개를 탐지합니다.",
        risk_level="중",
        fn=weekend_posting_test,
    ),
    AlgorithmSpec(
        id="threshold_avoidance",
        name="승인한도 회피 탐지",
        category="금액 패턴",
        description="흔한 승인 한도 금액 바로 아래 구간에 몰린 거래를 탐지합니다.",
        risk_level="상",
        fn=threshold_avoidance_test,
    ),
    AlgorithmSpec(
        id="related_party_keyword",
        name="특수관계자·고위험 키워드 탐지",
        category="텍스트/키워드",
        description="적요에 특수관계자, 접대, 소송 등 고위험 키워드가 포함된 거래를 탐지합니다.",
        risk_level="상",
        fn=related_party_keyword_test,
    ),
    AlgorithmSpec(
        id="duplicate_transaction",
        name="중복 지급 의심 탐지",
        category="전표 무결성",
        description="동일 거래처·동일 금액이 반복 청구된 거래를 탐지합니다.",
        risk_level="중",
        fn=duplicate_transaction_test,
    ),
    AlgorithmSpec(
        id="statistical_outlier",
        name="계정별 통계적 이상치 탐지",
        category="통계적 이상",
        description="계정과목 내 금액 분포에서 Z-score 3 이상인 이상치를 탐지합니다.",
        risk_level="중",
        fn=statistical_outlier_test,
    ),
    AlgorithmSpec(
        id="period_end_concentration",
        name="월말 집중 전기 탐지",
        category="시점 분석",
        description="매월 마지막 3일에 비정상적으로 몰린 전기를 탐지합니다.",
        risk_level="중",
        fn=period_end_concentration_test,
    ),
    AlgorithmSpec(
        id="doc_num_gap",
        name="전표번호 결번 탐지",
        category="전표 무결성",
        description="전표번호 순번에서 빠진 번호(결번)를 탐지합니다.",
        risk_level="상",
        fn=doc_num_gap_test,
    ),
    AlgorithmSpec(
        id="account_spike",
        name="계정별 월간 급증 탐지",
        category="통계적 이상",
        description="특정 계정의 월 합계가 다른 달 평균보다 3배 이상 급증한 구간을 탐지합니다.",
        risk_level="중",
        fn=account_spike_test,
    ),
]

ALGORITHM_MAP = {spec.id: spec for spec in ALGORITHMS}
