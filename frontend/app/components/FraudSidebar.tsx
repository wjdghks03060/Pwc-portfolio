'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { ShieldAlert, ChevronDown, RefreshCcw, Eye, EyeOff, Loader2 } from 'lucide-react';
import { apiUrl } from '../lib/api';
import { useAuditStore, FraudAlgorithm } from '../store';

const RISK_STYLES: Record<string, string> = {
  상: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
  중: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  하: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
};

interface FraudSidebarProps {
  onRunAlgorithm: (algorithmId: string) => void;
  disabled: boolean;
}

export default function FraudSidebar({ onRunAlgorithm, disabled }: FraudSidebarProps) {
  const [algorithms, setAlgorithms] = useState<FraudAlgorithm[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({});

  const {
    activeAlgorithmId,
    isFraudCheckRunning,
    fraudResult,
    flaggedDocNums,
    showFlaggedOnly,
    toggleShowFlaggedOnly,
    clearFraudResult,
  } = useAuditStore();

  useEffect(() => {
    fetch(apiUrl('/api/fraud-algorithms'))
      .then((res) => {
        if (!res.ok) throw new Error('failed');
        return res.json();
      })
      .then((data) => setAlgorithms(data.algorithms ?? []))
      .catch(() => setLoadError(true));
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, FraudAlgorithm[]>();
    for (const algo of algorithms) {
      if (!map.has(algo.category)) map.set(algo.category, []);
      map.get(algo.category)!.push(algo);
    }
    return Array.from(map.entries());
  }, [algorithms]);

  const toggleCategory = (category: string) =>
    setCollapsedCategories((prev) => ({ ...prev, [category]: !prev[category] }));

  return (
    <div className="w-[280px] h-full bg-slate-900 border-r border-slate-800 flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-800 flex items-center gap-2 bg-slate-900/50">
        <ShieldAlert className="text-rose-400 w-5 h-5" />
        <h2 className="font-bold">부정징후 탐지 알고리즘</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loadError && (
          <p className="text-xs text-rose-400 p-3">
            알고리즘 목록을 불러오지 못했습니다. 백엔드 서버(FastAPI)가 실행 중인지 확인해 주세요.
          </p>
        )}

        {grouped.map(([category, items]) => {
          const collapsed = collapsedCategories[category];
          return (
            <div key={category} className="mb-2">
              <button
                onClick={() => toggleCategory(category)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-bold text-slate-400 uppercase tracking-wide hover:text-slate-200"
              >
                {category}
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${collapsed ? '-rotate-90' : ''}`} />
              </button>
              {!collapsed && (
                <div className="flex flex-col gap-1">
                  {items.map((algo) => {
                    const isActive = activeAlgorithmId === algo.id;
                    const isRunning = isFraudCheckRunning && isActive;
                    return (
                      <button
                        key={algo.id}
                        disabled={disabled || isFraudCheckRunning}
                        onClick={() => onRunAlgorithm(algo.id)}
                        title={algo.description}
                        className={`text-left px-3 py-2 rounded-lg text-sm transition border ${
                          isActive
                            ? 'bg-indigo-600/20 border-indigo-500/50 text-indigo-200'
                            : 'border-transparent hover:bg-slate-800 text-slate-300'
                        } disabled:opacity-40 disabled:cursor-not-allowed`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">{algo.name}</span>
                          {isRunning ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-300 shrink-0" />
                          ) : (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${
                                RISK_STYLES[algo.risk_level] ?? RISK_STYLES['하']
                              }`}
                            >
                              위험도 {algo.risk_level}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-2">{algo.description}</p>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {fraudResult && (
        <div className="border-t border-slate-800 p-3 bg-slate-950/60 flex flex-col gap-2 max-h-[45%] overflow-y-auto">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-300">{fraudResult.algorithm_name}</span>
            <button onClick={clearFraudResult} className="text-slate-500 hover:text-slate-300" title="검사 결과 초기화">
              <RefreshCcw className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">{fraudResult.explanation}</p>
          <div className="flex items-center justify-between text-[11px] text-slate-400 bg-slate-900 rounded-lg px-2 py-1.5">
            <span>
              플래그 <span className="text-rose-400 font-bold">{fraudResult.flagged_count.toLocaleString()}</span>건 /
              전체 {fraudResult.total_count.toLocaleString()}건
            </span>
          </div>
          <button
            onClick={toggleShowFlaggedOnly}
            disabled={!flaggedDocNums || flaggedDocNums.size === 0}
            className={`flex items-center justify-center gap-1.5 text-xs font-semibold py-2 rounded-lg transition disabled:opacity-40 ${
              showFlaggedOnly ? 'bg-rose-600 hover:bg-rose-500 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
            }`}
          >
            {showFlaggedOnly ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {showFlaggedOnly ? '전체 분개 보기' : '플래그된 분개만 보기'}
          </button>
        </div>
      )}
    </div>
  );
}
