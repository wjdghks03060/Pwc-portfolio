'use client';

import React, { useMemo } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { JournalEntry } from '../store';
import { parseStdDate, formatKRW, monthKey } from '../lib/utils';

export interface DynamicChart {
  type: string;
  title: string;
  data: { x: string; y: number }[];
}

interface VisualizationProps {
  data: JournalEntry[];
  dynamicChart: DynamicChart | null;
}

const COLORS = ['#34d399', '#60a5fa', '#f472b6', '#fbbf24', '#a78bfa', '#f87171', '#22d3ee', '#facc15'];

const tooltipStyle = { background: '#0f172a', border: '1px solid #1e293b', fontSize: 12, borderRadius: 8 };
const axisTick = { fill: '#94a3b8', fontSize: 10 };

export default function Visualization({ data, dynamicChart }: VisualizationProps) {
  const monthlyTrend = useMemo(() => {
    const map = new Map<string, number>();
    data.forEach((row) => {
      const d = parseStdDate(row.std_date);
      if (!d) return;
      const key = monthKey(d);
      const amt = (row.std_debit_amt || 0) + (row.std_credit_amt || 0);
      map.set(key, (map.get(key) || 0) + amt);
    });
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, amount]) => ({ month, amount }));
  }, [data]);

  const topVendors = useMemo(() => aggregateTop(data, (r) => r.std_vendor), [data]);
  const topAccounts = useMemo(() => aggregateTop(data, (r) => r.std_account_code), [data]);

  if (data.length === 0 && !dynamicChart) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500 text-sm text-center px-6">
        원장을 업로드하고 컬럼 매핑을 완료하면 이 영역에 자동으로 데이터 시각화 분석이 표시됩니다.
      </div>
    );
  }

  if (dynamicChart) {
    return (
      <div className="h-full flex flex-col">
        <div className="text-xs font-bold text-slate-300 border-b border-slate-800 pb-1 mb-1 px-1">
          {dynamicChart.title}
        </div>
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dynamicChart.data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="x" tick={axisTick} />
              <YAxis tick={axisTick} tickFormatter={(v) => formatKRW(Number(v))} width={56} />
              <Tooltip formatter={(v: number) => formatKRW(v)} contentStyle={tooltipStyle} />
              <Bar dataKey="y" radius={[4, 4, 0, 0]}>
                {dynamicChart.data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full grid grid-cols-3 gap-3">
      <ChartCard title="월별 거래 추이">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={monthlyTrend} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorAmt" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#34d399" stopOpacity={0.5} />
                <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="month" tick={axisTick} />
            <YAxis tick={axisTick} tickFormatter={(v) => formatKRW(Number(v))} width={50} />
            <Tooltip formatter={(v: number) => formatKRW(v)} contentStyle={tooltipStyle} />
            <Area type="monotone" dataKey="amount" stroke="#34d399" fill="url(#colorAmt)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="상위 거래처 발생액">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={topVendors} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
            <XAxis type="number" tick={axisTick} tickFormatter={(v) => formatKRW(Number(v))} />
            <YAxis type="category" dataKey="label" width={72} tick={axisTick} />
            <Tooltip formatter={(v: number) => formatKRW(v)} contentStyle={tooltipStyle} />
            <Bar dataKey="amount" radius={[0, 4, 4, 0]}>
              {topVendors.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="계정과목별 발생액">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={topAccounts} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
            <XAxis type="number" tick={axisTick} tickFormatter={(v) => formatKRW(Number(v))} />
            <YAxis type="category" dataKey="label" width={72} tick={axisTick} />
            <Tooltip formatter={(v: number) => formatKRW(v)} contentStyle={tooltipStyle} />
            <Bar dataKey="amount" radius={[0, 4, 4, 0]}>
              {topAccounts.map((_, i) => (
                <Cell key={i} fill={COLORS[(i + 3) % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

function aggregateTop(
  data: JournalEntry[],
  keyFn: (row: JournalEntry) => string | undefined,
  limit = 6
): { label: string; amount: number }[] {
  const map = new Map<string, number>();
  data.forEach((row) => {
    const key = keyFn(row);
    if (!key) return;
    const amt = (row.std_debit_amt || 0) + (row.std_credit_amt || 0);
    map.set(key, (map.get(key) || 0) + amt);
  });
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label, amount]) => ({ label, amount }));
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 flex flex-col overflow-hidden">
      <div className="text-[11px] font-semibold text-slate-400 mb-1 px-1">{title}</div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
