/**
 * 백엔드가 반환하는 std_date 는 원본 컬럼 형식(예: "2025-01-01")이거나
 * epoch 타임스탬프 숫자 문자열일 수 있다. 두 경우를 모두 안전하게 Date로 변환한다.
 */
export function parseStdDate(raw: unknown): Date | null {
  if (raw === null || raw === undefined || raw === '') return null;

  const asNum = Number(raw);
  if (!Number.isNaN(asNum) && asNum > 1_000_000) {
    const fromEpoch = new Date(asNum);
    if (!Number.isNaN(fromEpoch.getTime())) return fromEpoch;
  }

  const fromString = new Date(String(raw));
  return Number.isNaN(fromString.getTime()) ? null : fromString;
}

export function formatKRW(value: number): string {
  if (!Number.isFinite(value)) return '0';
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `₩${(value / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `₩${(value / 10_000).toFixed(0)}만`;
  return `₩${value.toLocaleString()}`;
}

export function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}
