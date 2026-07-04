'use client';

import React from 'react';
import { useAuditStore } from './store';

export default function DashboardCharts() {
  const { globalData, setVendorFilter, selectedVendor } = useAuditStore();

  const vendorSales = globalData.reduce((acc, curr) => {
    const amount = (curr.std_credit_amt || 0) + (curr.std_debit_amt || 0);
    if (amount > 0 && curr.std_vendor) {
      acc[curr.std_vendor] = (acc[curr.std_vendor] || 0) + amount;
    }
    return acc;
  }, {} as Record<string, number>);

  const chartData = Object.entries(vendorSales)
    .map(([vendor, amount]) => ({ vendor, amount }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 10);

  const maxAmount = chartData.length > 0 ? Math.max(...chartData.map(d => d.amount)) : 1;

  return (
    <div className="h-full bg-slate-900 flex flex-col p-2">
      <div className="text-sm font-bold text-slate-200 mb-2">Top 10 거래처 발생액 분석 (클릭 시 필터링)</div>
      {chartData.length > 0 ? (
        <div className="flex-1 overflow-y-auto flex flex-col gap-2">
          {chartData.map((d) => (
            <div 
              key={d.vendor} 
              className={`flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-slate-800 ${selectedVendor === d.vendor ? 'bg-slate-800 ring-1 ring-emerald-500' : ''}`}
              onClick={() => setVendorFilter(d.vendor === selectedVendor ? null : d.vendor)}
            >
              <div className="w-24 text-xs text-slate-400 truncate" title={d.vendor}>{d.vendor}</div>
              <div className="flex-1 h-4 bg-slate-800 rounded overflow-hidden">
                <div 
                  className="h-full bg-emerald-500 transition-all" 
                  style={{ width: `${(d.amount / maxAmount) * 100}%` }}
                />
              </div>
              <div className="text-xs text-slate-300 w-24 text-right">
                ₩{(d.amount / 10000).toLocaleString()}만
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
          데이터 매핑 후 차트가 표시됩니다.
        </div>
      )}
    </div>
  );
}