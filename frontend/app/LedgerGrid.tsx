'use client';

import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ModuleRegistry, ColDef } from 'ag-grid-community'; 
import { useAuditStore } from './store';

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';

ModuleRegistry.registerModules([AllCommunityModule]);

interface LedgerGridProps {
  gridRef: React.RefObject<any>;
}

export default function LedgerGrid({ gridRef }: LedgerGridProps) {
  const { filteredData } = useAuditStore();

  const defaultColDef = useMemo<ColDef>(() => ({
    resizable: true,
    sortable: true,
    floatingFilter: true,
    filter: 'agTextColumnFilter',
    cellStyle: { borderRight: '1px solid #334155', borderBottom: '1px solid #334155' }
  }), []);

  const columnDefs = useMemo<ColDef[]>(() => [
    { 
      field: 'std_date', 
      headerName: '전기일자', 
      width: 150,
      filter: 'agDateColumnFilter',
      valueGetter: (params) => {
        if (!params.data || !params.data.std_date) return null;
        const d = new Date(Number(params.data.std_date));
        return isNaN(d.getTime()) ? null : d;
      },
      valueFormatter: (params) => {
        if (!params.value) return '';
        return params.value.toISOString().split('T')[0];
      }
    },
    { field: 'std_doc_num', headerName: '전표번호', width: 140 },
    { field: 'std_account_code', headerName: '계정과목', width: 160 },
    { field: 'std_vendor', headerName: '거래처', width: 180 },
    { 
      field: 'std_debit_amt', 
      headerName: '차변금액', 
      filter: 'agNumberColumnFilter',
      valueFormatter: (params) => params.value ? params.value.toLocaleString() : '0',
      width: 150,
      cellStyle: { textAlign: 'right', color: '#93c5fd', borderRight: '1px solid #334155', borderBottom: '1px solid #334155' }
    },
    { 
      field: 'std_credit_amt', 
      headerName: '대변금액', 
      filter: 'agNumberColumnFilter',
      valueFormatter: (params) => params.value ? params.value.toLocaleString() : '0',
      width: 150,
      cellStyle: { textAlign: 'right', color: '#6ee7b7', borderRight: '1px solid #334155', borderBottom: '1px solid #334155' }
    },
    { field: 'std_desc', headerName: '적요 (키워드 입력)', flex: 1, filter: 'agTextColumnFilter' },
  ], []);

  return (
      // 💡 이미 여기서 테마(ag-theme-quartz-dark)를 씌워주고 있으므로 충분합니다!
      <div className="ag-theme-quartz-dark w-full h-full">
        <AgGridReact
          ref={gridRef}
          theme="legacy"
          rowData={filteredData}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          pagination={true}
          paginationPageSize={100}
        />
      </div>
    );
  }