'use client';

import React, { useState, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { useAuditStore, JournalEntry } from './store';
import { Bot, BarChart3, TableProperties, Upload, FileSpreadsheet, Send, RotateCcw, Download } from 'lucide-react';
import MappingModal from './MappingModal';
import LedgerGrid from './LedgerGrid';
import FraudSidebar from './components/FraudSidebar';
import Visualization, { DynamicChart } from './components/Visualization';
import { apiUrl } from './lib/api';
import { exportLedgerCsv } from './lib/exportCsv';

const AI_WELCOME_MESSAGE =
  '안녕하세요, 회계사님! \n원장을 분석할 준비가 되었습니다.\n\n💡 추천 명령:\n1. "전기일자 6월 삼성전자 거래처를 추출해줘"\n2. "이걸 다시 월별 추이액 차트로 그려줘"';

export default function AuditDashboard() {
  const {
    uploadedFileName,
    setUploadInfo,
    mapping,
    setGlobalData,
    globalData,
    baseData,
    filteredData,
    flaggedDocNums,
    fraudResult,
    restoreBaseData,
    setFraudCheckRunning,
    setFraudResult,
    clearFraudResult,
  } = useAuditStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([
    { role: 'assistant', content: AI_WELCOME_MESSAGE }
  ]);
  const [input, setInput] = useState('');
  const [isAiThinking, setIsAiThinking] = useState(false);

  const [dynamicChart, setDynamicChart] = useState<DynamicChart | null>(null);

  const gridRef = useRef<AgGridReact<JournalEntry>>(null);

  const clearGridColumnFilters = () => {
    if (gridRef.current && gridRef.current.api) {
      gridRef.current.api.setFilterModel(null);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(apiUrl('/api/upload'), {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '업로드 실패');

      clearFraudResult();
      setDynamicChart(null);
      setMessages([{ role: 'assistant', content: AI_WELCOME_MESSAGE }]);
      setUploadInfo(data.file_name, data.columns);
      setIsModalOpen(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : '알 수 없는 오류';
      alert(`백엔드 통신 실패: ${message}\n(백엔드 서버가 http://localhost:8000 에서 실행 중인지 확인해 주세요.)`);
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const handleResetFilters = () => {
    restoreBaseData();
    clearGridColumnFilters();
    setDynamicChart(null);
  };

  const handleResetAiChat = () => {
    setMessages([{ role: 'assistant', content: AI_WELCOME_MESSAGE }]);
    setInput('');
    restoreBaseData();
    clearGridColumnFilters();
    setDynamicChart(null);
  };

  /** AG Grid 컬럼 필터까지 반영된 '지금 보이는' 행 */
  const getVisibleGridRows = (): JournalEntry[] => {
    const api = gridRef.current?.api;
    if (!api) return filteredData;
    const rows: JournalEntry[] = [];
    api.forEachNodeAfterFilterAndSort((node) => {
      if (node.data) rows.push(node.data);
    });
    return rows;
  };

  const handleExportVisibleCsv = () => {
    const rows = getVisibleGridRows();
    const condition = fraudResult
      ? `화면표시|부정징후=${fraudResult.algorithm_name}`
      : '화면표시(그리드 필터 포함)';
    exportLedgerCsv(rows, {
      prefix: 'ledger_export',
      sourceFile: uploadedFileName,
      condition,
      label: fraudResult?.algorithm_name ?? 'grid',
    });
  };

  const handleExportFlaggedCsv = () => {
    if (!flaggedDocNums || flaggedDocNums.size === 0) {
      alert('플래그된 분개가 없습니다. 먼저 부정징후 알고리즘을 실행해 주세요.');
      return;
    }
    const source = baseData.length > 0 ? baseData : globalData;
    const rows = source.filter((row) => flaggedDocNums.has(String(row.std_doc_num)));
    exportLedgerCsv(rows, {
      prefix: 'fraud_flagged',
      sourceFile: uploadedFileName,
      condition: fraudResult?.algorithm_name ?? '부정징후 플래그',
      label: fraudResult?.algorithm_name ?? 'flagged',
    });
  };

  const handleRunFraudCheck = async (algorithmId: string) => {
    if (!uploadedFileName || !mapping) {
      alert('먼저 원장 CSV를 업로드하고 컬럼 매핑을 완료해 주세요.');
      return;
    }
    // AI 질의로 줄어든 그리드를 원본으로 되돌린 뒤 부정징후 하이라이트를 적용
    restoreBaseData();
    clearGridColumnFilters();
    setFraudCheckRunning(true, algorithmId);
    setDynamicChart(null);
    try {
      const res = await fetch(apiUrl('/api/fraud-check'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: uploadedFileName, mapping, algorithm: algorithmId }),
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || '부정징후 검사 실패');

      const flagged: JournalEntry[] = JSON.parse(result.data);
      setFraudResult(
        {
          algorithm: result.algorithm,
          algorithm_name: result.algorithm_name,
          explanation: result.explanation,
          flagged_count: result.flagged_count,
          total_count: result.total_count,
          stats: result.stats,
        },
        flagged.map((f) => String(f.std_doc_num))
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : '알 수 없는 오류';
      alert(`부정징후 검사 실패: ${message}`);
      setFraudCheckRunning(false, null);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !uploadedFileName || !mapping) return;

    const userMsg = input;
    const chatHistory = messages.map(m => ({ role: m.role, content: m.content }));
    chatHistory.push({ role: 'user', content: userMsg });

    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setInput('');
    setIsAiThinking(true);

    try {
      const res = await fetch(apiUrl('/api/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: uploadedFileName,
          message: userMsg,
          history: chatHistory,
          mapping: mapping
        })
      });

      const result = await res.json();
      setIsAiThinking(false);

      if (result.success) {
        const parsedData: JournalEntry[] = JSON.parse(result.data || '[]');
        const isEmpty = Boolean(result.empty) || parsedData.length === 0;

        if (isEmpty) {
          // 0건이면 원장을 비우지 않고 안내만 표시 (기존 그리드 유지)
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content:
                (result.explanation || '조회 결과가 없습니다.') +
                '\n\n※ 결과가 0건이라 원장 그리드는 그대로 유지했습니다. 조건을 바꿔 다시 질문해 주세요.',
            },
          ]);
          setDynamicChart(null);
        } else {
          setMessages(prev => [...prev, { role: 'assistant', content: result.explanation }]);
          setGlobalData(parsedData);
          clearFraudResult();

          if (result.requires_chart && parsedData.length > 0) {
            const xKey = result.chart_x;
            const yKey = result.chart_y;

            const summary: Record<string, number> = {};
            parsedData.forEach((row) => {
              const rowRecord = row as unknown as Record<string, unknown>;
              let xVal = String(rowRecord[xKey] ?? '기타');

              if (xKey === 'std_date' && xVal !== '기타') {
                const d = new Date(Number(xVal) || xVal);
                if (!isNaN(d.getTime())) {
                  xVal = d.toISOString().substring(0, 7);
                }
              }
              summary[xVal] = (summary[xVal] || 0) + (Number(rowRecord[yKey]) || 0);
            });

            const chartRows = Object.entries(summary)
              .map(([x, y]) => ({ x, y }))
              .sort((a, b) => a.x.localeCompare(b.x))
              .slice(0, 8);

            setDynamicChart({
              type: result.chart_type,
              title: `AI 추출 시각화 [X축: ${xKey.replace('std_', '')} / Y축: ${yKey.replace('std_', '')}]`,
              data: chartRows
            });
          } else {
            setDynamicChart(null);
          }
        }
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: result.explanation }]);
      }
    } catch {
      setIsAiThinking(false);
      setMessages(prev => [...prev, { role: 'assistant', content: '백엔드 AI 서버 통신에 실패했습니다.' }]);
    }
  };

  const canResetLedger = baseData.length > 0;

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">

      <FraudSidebar
        onRunAlgorithm={handleRunFraudCheck}
        onExportFlagged={handleExportFlaggedCsv}
        disabled={!uploadedFileName || !mapping}
      />

      <div className="flex flex-col flex-1 h-full p-4 gap-4 overflow-hidden min-w-0">
        <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-xl">
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="text-emerald-400 w-6 h-6" />
            <div>
              <h1 className="font-bold text-md">전수조사 AI 감사 Agent</h1>
              <p className="text-xs text-slate-400">
                {uploadedFileName ? `활성 원장: ${uploadedFileName} ${mapping ? '(매핑 완료)' : '(매핑 대기중)'}` : '감사할 원장 CSV 파일을 업로드해 주세요.'}
              </p>
            </div>
          </div>

          <label className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer transition ${
            isUploading ? 'bg-slate-800 text-slate-500' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
          }`}>
            <Upload className="w-4 h-4" />
            {isUploading ? '분석 중...' : '원장 업로드 (.csv)'}
            <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" disabled={isUploading} />
          </label>
        </div>

        <div className="h-[280px] bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col">
          <div className="flex items-center gap-2 mb-2 text-emerald-400">
            <BarChart3 className="w-5 h-5" />
            <h2 className="font-bold">데이터 시각화 분석</h2>
          </div>

          <div className="flex-1 w-full bg-slate-950 border border-slate-800 rounded-lg p-3 overflow-hidden">
            <Visualization data={globalData} dynamicChart={dynamicChart} />
          </div>
        </div>

        <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-blue-400">
              <TableProperties className="w-5 h-5" />
              <h2 className="font-bold">원장 상세 그리드</h2>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleExportVisibleCsv}
                disabled={filteredData.length === 0}
                title="지금 그리드에 보이는 분개를 CSV로 내보냅니다"
                className="flex items-center gap-1 text-xs bg-emerald-700/80 border border-emerald-600/50 px-3 py-1.5 rounded-lg hover:bg-emerald-600 transition font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Download className="w-3.5 h-3.5" />
                CSV 내보내기
              </button>
              <button
                onClick={handleResetFilters}
                disabled={!canResetLedger}
                className="flex items-center gap-1 text-xs bg-slate-800 border border-slate-700 px-3 py-1.5 rounded-lg hover:bg-slate-700 transition font-medium text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
                전체 필터 초기화
              </button>
            </div>
          </div>
          <div className="flex-1 w-full overflow-hidden rounded-lg">
             <LedgerGrid gridRef={gridRef} />
          </div>
        </div>
      </div>

      <div className="w-[380px] h-full bg-slate-900 border-l border-slate-800 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between gap-2 bg-slate-900/50">
          <div className="flex items-center gap-2 min-w-0">
            <Bot className="text-indigo-400 w-5 h-5 shrink-0" />
            <h2 className="font-bold truncate">AI 원장 질의 Agent</h2>
          </div>
          <button
            type="button"
            onClick={handleResetAiChat}
            disabled={!canResetLedger && messages.length <= 1}
            title="대화와 원장 필터를 초기화합니다"
            className="flex items-center gap-1 text-[11px] bg-slate-800 border border-slate-700 px-2.5 py-1 rounded-lg hover:bg-slate-700 transition font-medium text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          >
            <RotateCcw className="w-3 h-3 text-slate-400" />
            초기화
          </button>
        </div>

        <div className="flex-1 p-4 overflow-y-auto flex flex-col gap-3 bg-slate-950/40">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex flex-col max-w-[85%] rounded-xl p-3 text-sm ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white self-end rounded-tr-none shadow-md'
                : 'bg-slate-800 text-slate-200 self-start rounded-tl-none border border-slate-700 shadow-md'
            }`}>
              <span className="text-[10px] opacity-60 mb-1 font-bold">{msg.role === 'user' ? '회계사' : '감사 AI Agent'}</span>
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          ))}
          {isAiThinking && (
            <div className="bg-slate-800 text-slate-400 self-start rounded-xl rounded-tl-none p-3 text-sm border border-slate-700 animate-pulse">
              AI 회계사가 감사 데이터베이스(DuckDB) 쿼리 및 회계적 절차를 검토 중입니다...
            </div>
          )}
        </div>

        <form onSubmit={handleSendMessage} className="p-3 border-t border-slate-800 bg-slate-900 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={uploadedFileName ? "예시: 통신비 내역 뽑아줘" : "먼저 원장을 업로드해 주세요"}
            disabled={!uploadedFileName || isAiThinking}
            className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!uploadedFileName || isAiThinking}
            className="bg-indigo-600 hover:bg-indigo-500 text-white p-2.5 rounded-xl transition disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      <MappingModal key={uploadedFileName ?? 'no-file'} isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
    </div>
  );
}
