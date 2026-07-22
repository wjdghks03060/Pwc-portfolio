import type { JournalEntry } from '../store';

/** 그리드/워킹페이퍼용 한글 컬럼 순서 */
export const CSV_COLUMNS: { key: keyof JournalEntry; header: string }[] = [
  { key: 'std_date', header: '전기일자' },
  { key: 'std_doc_num', header: '전표번호' },
  { key: 'std_account_code', header: '계정과목' },
  { key: 'std_vendor', header: '거래처' },
  { key: 'std_debit_amt', header: '차변금액' },
  { key: 'std_credit_amt', header: '대변금액' },
  { key: 'std_desc', header: '적요' },
];

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function stamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
}

function sanitizeFilePart(text: string): string {
  return text.replace(/[\\/:*?"<>|\s]+/g, '_').replace(/_+/g, '_').slice(0, 40);
}

/** Excel 한글 호환을 위해 UTF-8 BOM 포함 CSV 문자열 생성 */
export function buildLedgerCsv(
  rows: JournalEntry[],
  meta?: { sourceFile?: string | null; condition?: string | null }
): string {
  const lines: string[] = [];
  if (meta?.sourceFile || meta?.condition) {
    const note = [
      meta.sourceFile ? `원본=${meta.sourceFile}` : null,
      meta.condition ? `조건=${meta.condition}` : null,
      `건수=${rows.length}`,
      `내보낸시각=${new Date().toISOString()}`,
    ]
      .filter(Boolean)
      .join(' | ');
    lines.push(`# ${note}`);
  }
  lines.push(CSV_COLUMNS.map((c) => c.header).join(','));
  for (const row of rows) {
    lines.push(CSV_COLUMNS.map((c) => escapeCsvCell(row[c.key])).join(','));
  }
  return `\uFEFF${lines.join('\r\n')}`;
}

export function downloadCsv(filename: string, csvContent: string): void {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function buildExportFilename(opts: {
  prefix: string;
  count: number;
  label?: string | null;
}): string {
  const parts = [opts.prefix, stamp()];
  if (opts.label) parts.push(sanitizeFilePart(opts.label));
  parts.push(`${opts.count}건`);
  return `${parts.join('_')}.csv`;
}

export function exportLedgerCsv(
  rows: JournalEntry[],
  opts: {
    prefix: string;
    sourceFile?: string | null;
    condition?: string | null;
    label?: string | null;
  }
): void {
  if (rows.length === 0) {
    alert('내보낼 데이터가 없습니다.');
    return;
  }
  const csv = buildLedgerCsv(rows, {
    sourceFile: opts.sourceFile,
    condition: opts.condition ?? opts.label,
  });
  const filename = buildExportFilename({
    prefix: opts.prefix,
    count: rows.length,
    label: opts.label,
  });
  downloadCsv(filename, csv);
}
