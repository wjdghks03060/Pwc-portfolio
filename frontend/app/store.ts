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
  /** 매핑 직후 원본 원장. AI 질의로 globalData가 줄어들어도 복구 기준으로 유지 */
  baseData: JournalEntry[];
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
  /** 매핑 완료 시 원본 원장을 저장하고 그리드에도 동일하게 로드 */
  setBaseData: (data: JournalEntry[]) => void;
  /** AI 질의/필터로 줄어든 globalData를 원본 원장으로 복구 */
  restoreBaseData: () => void;
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
  baseData: [],
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

  setBaseData: (data) =>
    set((state) => ({
      baseData: data,
      globalData: data,
      selectedVendor: null,
      fraudResult: null,
      flaggedDocNums: null,
      activeAlgorithmId: null,
      showFlaggedOnly: false,
      filteredData: computeFiltered({
        ...state,
        globalData: data,
        selectedVendor: null,
        flaggedDocNums: null,
        showFlaggedOnly: false,
      }),
    })),

  restoreBaseData: () =>
    set((state) => ({
      globalData: state.baseData,
      selectedVendor: null,
      fraudResult: null,
      flaggedDocNums: null,
      activeAlgorithmId: null,
      showFlaggedOnly: false,
      filteredData: computeFiltered({
        ...state,
        globalData: state.baseData,
        selectedVendor: null,
        flaggedDocNums: null,
        showFlaggedOnly: false,
      }),
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
