import { create } from 'zustand';

export interface JournalEntry {
  std_doc_num: string;
  std_date: string;
  std_account_code: string;
  std_vendor: string;
  std_debit_amt: number;
  std_credit_amt: number;
  std_desc: string;
}

// 회계사가 매핑한 컬럼 위치를 저장할 타입
export interface ColumnMapping {
  doc_num: string;
  date: string;
  account_code: string;
  vendor: string;
  debit_amt: string;
  credit_amt: string;
  desc: string;
}

interface AuditState {
  globalData: JournalEntry[];
  filteredData: JournalEntry[];
  selectedVendor: string | null;
  uploadedFileName: string | null;
  availableColumns: string[]; // CSV 파일에서 추출한 실제 컬럼 목록
  mapping: ColumnMapping | null;

  setGlobalData: (data: JournalEntry[]) => void;
  setVendorFilter: (vendor: string | null) => void;
  setUploadInfo: (fileName: string, columns: string[]) => void;
  setMapping: (mapping: ColumnMapping) => void;
}

export const useAuditStore = create<AuditState>((set) => ({
  globalData: [],
  filteredData: [],
  selectedVendor: null,
  uploadedFileName: null,
  availableColumns: [],
  mapping: null,

  setGlobalData: (data) => set({ globalData: data, filteredData: data }),
  
  setVendorFilter: (vendor) => set((state) => ({
    selectedVendor: vendor,
    filteredData: vendor 
      ? state.globalData.filter(d => d.std_vendor === vendor) 
      : state.globalData
  })),

  setUploadInfo: (fileName, columns) => set({
    uploadedFileName: fileName,
    availableColumns: columns
  }),

  setMapping: (mapping) => set({ mapping })
}));