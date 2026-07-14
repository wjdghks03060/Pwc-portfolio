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

export interface FraudAlgorithm {
  id: string;
  name: string;
  category: string;
  description: string;
  risk_level: string;
}

export interface FraudCheckResult {
  algorithm: string;
  algorithm_name: string;
  explanation: string;
  flagged_count: number;
  total_count: number;
  stats: Record<string, unknown>;
}

interface AuditState {
  globalData: JournalEntry[];
  filteredData: JournalEntry[];
  selectedVendor: string | null;
  uploadedFileName: string | null;
  availableColumns: string[]; // CSV 파일에서 추출한 실제 컬럼 목록
  mapping: ColumnMapping | null;

  // 부정징후 탐지 관련 상태
  activeAlgorithmId: string | null;
  fraudResult: FraudCheckResult | null;
  flaggedDocNums: Set<string> | null;
  showFlaggedOnly: boolean;
  isFraudCheckRunning: boolean;

  setGlobalData: (data: JournalEntry[]) => void;
  setVendorFilter: (vendor: string | null) => void;
  setUploadInfo: (fileName: string, columns: string[]) => void;
  setMapping: (mapping: ColumnMapping) => void;

  setFraudCheckRunning: (running: boolean, algorithmId?: string | null) => void;
  setFraudResult: (result: FraudCheckResult, flaggedDocNums: string[]) => void;
  clearFraudResult: () => void;
  toggleShowFlaggedOnly: () => void;
}

function computeFiltered(state: {
  globalData: JournalEntry[];
  selectedVendor: string | null;
  showFlaggedOnly: boolean;
  flaggedDocNums: Set<string> | null;
}): JournalEntry[] {
  let data = state.globalData;
  if (state.selectedVendor) {
    data = data.filter((d) => d.std_vendor === state.selectedVendor);
  }
  if (state.showFlaggedOnly && state.flaggedDocNums) {
    data = data.filter((d) => state.flaggedDocNums!.has(String(d.std_doc_num)));
  }
  return data;
}

export const useAuditStore = create<AuditState>((set) => ({
  globalData: [],
  filteredData: [],
  selectedVendor: null,
  uploadedFileName: null,
  availableColumns: [],
  mapping: null,

  activeAlgorithmId: null,
  fraudResult: null,
  flaggedDocNums: null,
  showFlaggedOnly: false,
  isFraudCheckRunning: false,

  setGlobalData: (data) =>
    set((state) => ({
      globalData: data,
      filteredData: computeFiltered({ ...state, globalData: data }),
    })),

  setVendorFilter: (vendor) =>
    set((state) => ({
      selectedVendor: vendor,
      filteredData: computeFiltered({ ...state, selectedVendor: vendor }),
    })),

  setUploadInfo: (fileName, columns) =>
    set({
      uploadedFileName: fileName,
      availableColumns: columns,
    }),

  setMapping: (mapping) => set({ mapping }),

  setFraudCheckRunning: (running, algorithmId) =>
    set({ isFraudCheckRunning: running, ...(algorithmId !== undefined ? { activeAlgorithmId: algorithmId } : {}) }),

  setFraudResult: (result, flaggedDocNums) =>
    set((state) => {
      const flaggedSet = new Set(flaggedDocNums.map(String));
      return {
        fraudResult: result,
        flaggedDocNums: flaggedSet,
        activeAlgorithmId: result.algorithm,
        isFraudCheckRunning: false,
        filteredData: computeFiltered({ ...state, flaggedDocNums: flaggedSet }),
      };
    }),

  clearFraudResult: () =>
    set((state) => ({
      fraudResult: null,
      flaggedDocNums: null,
      activeAlgorithmId: null,
      showFlaggedOnly: false,
      filteredData: computeFiltered({ ...state, flaggedDocNums: null, showFlaggedOnly: false }),
    })),

  toggleShowFlaggedOnly: () =>
    set((state) => {
      const next = !state.showFlaggedOnly;
      return {
        showFlaggedOnly: next,
        filteredData: computeFiltered({ ...state, showFlaggedOnly: next }),
      };
    }),
}));
