'use client';

import React, { useState } from 'react';
import { useAuditStore, ColumnMapping } from './store';
import { Columns } from 'lucide-react';
import { apiUrl } from './lib/api';

interface MappingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function MappingModal({ isOpen, onClose }: MappingModalProps) {
  const { availableColumns, setMapping, uploadedFileName } = useAuditStore();

  // 원본 CSV에 전표번호 열이 없을 경우, 업로드 시 백엔드가 자동 생성한 _row_id를
  // 기본값으로 미리 선택해 회계사의 매핑 작업을 줄여준다. (page.tsx에서 파일 업로드마다
  // key={uploadedFileName} 로 이 컴포넌트를 새로 마운트하므로, 최초 상태 계산에만
  // availableColumns를 참조해도 안전하다.)
  const [localMapping, setLocalMapping] = useState<ColumnMapping>(() => ({
    doc_num: availableColumns.includes('_row_id') ? '_row_id' : '',
    date: '', account_code: '', vendor: '',
    debit_amt: '', credit_amt: '', desc: ''
  }));

  if (!isOpen) return null;

  const handleSelect = (field: keyof ColumnMapping, value: string) => {
    setLocalMapping(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    if (Object.values(localMapping).some(v => v === '')) {
      alert('모든 필수 항목을 매핑해 주세요!');
      return;
    }
    
    setMapping(localMapping);
    
    try {
      const res = await fetch(apiUrl('/api/query-test'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: uploadedFileName,
          query_string: `SELECT 
            "${localMapping.date}" as std_date,
            "${localMapping.doc_num}" as std_doc_num,
            "${localMapping.account_code}" as std_account_code,
            "${localMapping.vendor}" as std_vendor,
            CAST("${localMapping.debit_amt}" AS DOUBLE) as std_debit_amt,
            CAST("${localMapping.credit_amt}" AS DOUBLE) as std_credit_amt,
            "${localMapping.desc}" as std_desc
            FROM ledger`
        }),
      });
      
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || '백엔드 응답 실패');

      const parsedData = JSON.parse(result.data);
      
      // 원본 원장으로 보관 — AI 질의로 globalData가 줄어들어도 복구 가능
      useAuditStore.getState().setBaseData(parsedData);
      
      onClose();
    } catch (e) {
      console.error(e);
      const message = e instanceof Error ? e.message : '알 수 없는 오류';
      alert(`데이터 로드 실패: ${message}`);
    }
  };

  const fields: { key: keyof ColumnMapping; label: string; desc: string }[] = [
    { key: 'doc_num', label: '전표번호', desc: '고유 전표 번호 열 (없다면 자동 생성된 _row_id 선택)' },
    { key: 'date', label: '전기일자', desc: '날짜 열 (YYYY-MM-DD)' },
    { key: 'account_code', label: '계정과목', desc: '계정 명칭/코드 열' },
    { key: 'vendor', label: '거래처', desc: '거래처명 열' },
    { key: 'debit_amt', label: '차변금액', desc: '차변 금액 열' },
    { key: 'credit_amt', label: '대변금액', desc: '대변 금액 열' },
    { key: 'desc', label: '적요', desc: '적요 설명 열' },
  ];

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 w-[550px] p-6 rounded-2xl shadow-2xl flex flex-col gap-4">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <Columns className="text-emerald-400 w-6 h-6" />
          <h3 className="text-lg font-bold">감사 데이터 매핑</h3>
        </div>
        <div className="flex flex-col gap-3 max-h-[400px] overflow-y-auto pr-2">
          {fields.map((f) => (
            <div key={f.key} className="flex flex-col">
              <label className="text-sm text-slate-300">{f.label}</label>
              <select
                value={localMapping[f.key]}
                onChange={(e) => handleSelect(f.key, e.target.value)}
                className="bg-slate-950 border border-slate-800 p-2 rounded text-sm"
              >
                <option value="">-- 선택 --</option>
                {availableColumns.map((col) => <option key={col} value={col}>{col}</option>)}
              </select>
              <span className="text-xs text-slate-500 mt-1">{f.desc}</span>
            </div>
          ))}
        </div>
        <button onClick={handleSubmit} className="bg-emerald-600 py-3 rounded-xl font-bold hover:bg-emerald-500">
          데이터 로드 실행
        </button>
      </div>
    </div>
  );
}