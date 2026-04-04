import axios from 'axios';
import type {
  Bank,
  BankAccount,
  Category,
  Transaction,
  TransactionListResponse,
  CategorizationRule,
  ImportBatch,
  ImportPreview,
  ImportResult,
  ImportAnalysis,
  OverlapCheckResponse,
  ColumnMapping,
  TransactionSuggestion,
  Projection,
  User,
  LoginResponse,
  DashboardSummary,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para adicionar token de autenticação
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor para tratar erros de autenticação
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return response.data;
  },

  register: async (data: { username: string; email: string; password: string; full_name?: string }): Promise<User> => {
    const response = await api.post('/auth/register', data);
    return response.data;
  },

  me: async (): Promise<User> => {
    const response = await api.get('/auth/me');
    return response.data;
  },
};

// Banks
export const banksApi = {
  list: async (): Promise<Bank[]> => {
    const response = await api.get('/banks');
    return response.data;
  },

  get: async (id: number): Promise<Bank> => {
    const response = await api.get(`/banks/${id}`);
    return response.data;
  },

  create: async (data: Partial<Bank>): Promise<Bank> => {
    const response = await api.post('/banks', data);
    return response.data;
  },

  update: async (id: number, data: Partial<Bank>): Promise<Bank> => {
    const response = await api.put(`/banks/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/banks/${id}`);
  },
};

// Accounts
export const accountsApi = {
  list: async (activeOnly = true): Promise<BankAccount[]> => {
    const response = await api.get('/accounts', { params: { active_only: activeOnly } });
    return response.data;
  },

  get: async (id: number): Promise<BankAccount> => {
    const response = await api.get(`/accounts/${id}`);
    return response.data;
  },

  getBalance: async (id: number): Promise<{ current_balance: number; calculated_balance: number; difference: number }> => {
    const response = await api.get(`/accounts/${id}/balance`);
    return response.data;
  },

  create: async (data: Partial<BankAccount>): Promise<BankAccount> => {
    const response = await api.post('/accounts', data);
    return response.data;
  },

  update: async (id: number, data: Partial<BankAccount>): Promise<BankAccount> => {
    const response = await api.put(`/accounts/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/accounts/${id}`);
  },

  recalculateBalance: async (id: number): Promise<void> => {
    await api.post(`/accounts/${id}/recalculate-balance`);
  },
};

// Categories
export const categoriesApi = {
  list: async (activeOnly = true, flat = false): Promise<Category[]> => {
    const response = await api.get('/categories', { params: { active_only: activeOnly, flat } });
    return response.data;
  },

  get: async (id: number): Promise<Category> => {
    const response = await api.get(`/categories/${id}`);
    return response.data;
  },

  create: async (data: Partial<Category>): Promise<Category> => {
    const response = await api.post('/categories', data);
    return response.data;
  },

  update: async (id: number, data: Partial<Category>): Promise<Category> => {
    const response = await api.put(`/categories/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/categories/${id}`);
  },
};

// Transactions
export const transactionsApi = {
  list: async (params?: {
    account_id?: number;
    category_id?: number;
    start_date?: string;
    end_date?: string;
    card_payment_start?: string;
    card_payment_end?: string;
    search?: string;
    is_validated?: boolean;
    page?: number;
    limit?: number;
  }): Promise<TransactionListResponse> => {
    const response = await api.get('/transactions', { params });
    return response.data;
  },

  getPending: async (accountId?: number, page = 1, limit = 50): Promise<Transaction[]> => {
    const response = await api.get('/transactions/pending', {
      params: { account_id: accountId, page, limit },
    });
    return response.data;
  },

  getPendingCount: async (): Promise<number> => {
    const response = await api.get('/transactions/pending/count');
    return response.data.count;
  },

  get: async (id: number): Promise<Transaction> => {
    const response = await api.get(`/transactions/${id}`);
    return response.data;
  },

  create: async (data: Partial<Transaction>): Promise<Transaction> => {
    const response = await api.post('/transactions', data);
    return response.data;
  },

  update: async (id: number, data: Partial<Transaction>): Promise<Transaction> => {
    const response = await api.put(`/transactions/${id}`, data);
    return response.data;
  },

  updateCategory: async (id: number, categoryId: number, createRule = false): Promise<void> => {
    await api.patch(`/transactions/${id}/category`, null, {
      params: { category_id: categoryId, create_rule: createRule },
    });
  },

  bulkCategorize: async (transactionIds: number[], categoryId: number): Promise<void> => {
    await api.patch('/transactions/bulk-categorize', {
      transaction_ids: transactionIds,
      category_id: categoryId,
    });
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/transactions/${id}`);
  },

  getSuggestion: async (id: number): Promise<TransactionSuggestion> => {
    const response = await api.get(`/transactions/${id}/suggestion`);
    return response.data;
  },
};

// Rules
export const rulesApi = {
  list: async (activeOnly = true, categoryId?: number): Promise<CategorizationRule[]> => {
    const response = await api.get('/rules', { params: { active_only: activeOnly, category_id: categoryId } });
    return response.data;
  },

  get: async (id: number): Promise<CategorizationRule> => {
    const response = await api.get(`/rules/${id}`);
    return response.data;
  },

  create: async (data: Partial<CategorizationRule>): Promise<CategorizationRule> => {
    const response = await api.post('/rules', data);
    return response.data;
  },

  update: async (id: number, data: Partial<CategorizationRule>): Promise<CategorizationRule> => {
    const response = await api.put(`/rules/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/rules/${id}`);
  },

  test: async (pattern: string, matchType: string, testText: string): Promise<{ matches: boolean; matched_text?: string }> => {
    const response = await api.post('/rules/test', {
      pattern,
      match_type: matchType,
      test_text: testText,
    });
    return response.data;
  },

  applyAll: async (): Promise<{ categorized: number; total_pending: number }> => {
    const response = await api.post('/rules/apply-all');
    return response.data;
  },

  seed: async (): Promise<{ rules_created: number; skipped_no_category: number; skipped_existing: number; total_active_rules: number }> => {
    const response = await api.post('/rules/seed');
    return response.data;
  },
};

// Imports
export const importsApi = {
  upload: async (file: File, accountId: number): Promise<ImportPreview> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('account_id', accountId.toString());
    const response = await api.post('/imports/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  process: async (data: {
    batch_id: number;
    column_mapping: ColumnMapping;
    account_id: number;
    validate_balance?: boolean;
    expected_final_balance?: number;
    skip_duplicates?: boolean;
    card_payment_date?: string;
  }): Promise<ImportResult> => {
    const response = await api.post('/imports/process', data);
    return response.data;
  },

  listBatches: async (accountId?: number): Promise<ImportBatch[]> => {
    const response = await api.get('/imports/batches', { params: { account_id: accountId } });
    return response.data;
  },

  getBatch: async (id: number): Promise<ImportBatch> => {
    const response = await api.get(`/imports/batches/${id}`);
    return response.data;
  },

  revertBatch: async (id: number): Promise<{ deleted_count: number }> => {
    const response = await api.delete(`/imports/batches/${id}`);
    return response.data;
  },

  analyze: async (data: {
    batch_id: number;
    column_mapping: ColumnMapping;
    account_id: number;
    card_payment_date?: string;
  }): Promise<ImportAnalysis> => {
    const response = await api.post('/imports/analyze', data);
    return response.data;
  },

  getTemplate: async (accountId: number): Promise<{ column_mapping: ColumnMapping; success_count: number } | null> => {
    const response = await api.get(`/imports/templates/${accountId}`);
    return response.data;
  },

  deleteTemplate: async (accountId: number): Promise<void> => {
    await api.delete(`/imports/templates/${accountId}`);
  },

  overlapCheck: async (accountId: number, startDate: string, endDate: string): Promise<OverlapCheckResponse> => {
    const response = await api.get('/imports/overlap-check', {
      params: { account_id: accountId, start_date: startDate, end_date: endDate },
    });
    return response.data;
  },
};

// Projections
export interface UncertainMatch {
  projected_id: number;
  projected_description: string;
  projected_amount: number;
  projected_date: string;
  matched_transaction_id: number | null;
  matched_description: string | null;
  matched_amount: number | null;
  matched_date: string | null;
  confidence: number;
}

export interface MonthlyProjection {
  account_id: number;
  account_name: string;
  month: string;
  current_balance: number;
  balance_at_month_start: number;
  projected_final_balance: number;
  entries: Array<{
    date: string;
    description: string;
    amount: number;
    category_name: string | null;
    category_color: string | null;
    type: 'real' | 'projected' | 'uncertain';
    id: number;
    is_recurring?: boolean;
  }>;
  daily_balances: Array<{
    date: string;
    balance: number;
    is_past: boolean;
  }>;
  real_count: number;
  projected_count: number;
  realized_count: number;
  uncertain_matches: UncertainMatch[];
}

export interface RecurringDetection {
  description: string;
  normalized_description: string;
  avg_amount: number;
  avg_day: number;
  std_day: number;
  day_is_fixed: boolean;
  occurrences: number;
  cv: number;
  category_id: number | null;
  category_name: string | null;
}

export const projectionsApi = {
  getMonthly: async (accountId: number, month: string): Promise<MonthlyProjection> => {
    const response = await api.get(`/projections/${accountId}/monthly`, {
      params: { month },
    });
    return response.data;
  },

  detectRecurring: async (accountId: number, minOccurrences = 3): Promise<RecurringDetection[]> => {
    const response = await api.post('/projections/detect-recurring', null, {
      params: { account_id: accountId, min_occurrences: minOccurrences },
    });
    return response.data;
  },

  confirmRecurring: async (accountId: number, items: Array<{
    description: string;
    amount: number;
    recurring_day: number;
    category_id?: number | null;
  }>): Promise<{ created_count: number }> => {
    const response = await api.post('/projections/confirm-recurring', items, {
      params: { account_id: accountId },
    });
    return response.data;
  },

  get: async (accountId: number, monthsAhead = 3, method = 'average'): Promise<{
    account_id: number;
    account_name: string;
    current_balance: number;
    method: string;
    projections: Projection[];
  }> => {
    const response = await api.get(`/projections/${accountId}`, {
      params: { months_ahead: monthsAhead, method },
    });
    return response.data;
  },

  getRecurring: async (accountId: number, minOccurrences = 3): Promise<Array<{
    description: string;
    amount: number;
    typical_day: number;
    occurrences: number;
    category_name?: string;
  }>> => {
    const response = await api.get(`/projections/${accountId}/recurring`, {
      params: { min_occurrences: minOccurrences },
    });
    return response.data;
  },

  createItem: async (item: {
    account_id: number;
    date: string;
    description: string;
    amount_brl: number;
    category_id?: number | null;
    is_recurring?: boolean;
    recurring_day?: number | null;
  }): Promise<{ id: number }> => {
    const response = await api.post('/projections/cash/items', item);
    return response.data;
  },

  updateItem: async (id: number, updates: {
    date?: string;
    description?: string;
    amount_brl?: number;
    category_id?: number | null;
    is_recurring?: boolean;
    recurring_day?: number | null;
  }): Promise<{ id: number }> => {
    const response = await api.put(`/projections/cash/items/${id}`, updates);
    return response.data;
  },

  deleteItem: async (id: number): Promise<void> => {
    await api.delete(`/projections/cash/items/${id}`);
  },

  confirmMatch: async (projectedId: number, action: 'confirm' | 'reject'): Promise<{ message: string; id: number }> => {
    const response = await api.post('/projections/confirm-match', null, {
      params: { projected_id: projectedId, action },
    });
    return response.data;
  },
};

// Reports
interface PivotRow {
  category_id: number;
  category_name: string;
  category_type: string;
  category_color: string | null;
  values: Record<string, number>;
  total: number;
}

interface GroupTotals {
  values: Record<string, number>;
  total: number;
}

export interface PivotReport {
  start_month: string;
  end_month: string;
  currency: string;
  months: string[];
  expense_rows: PivotRow[];
  expense_totals: GroupTotals;
  income_rows: PivotRow[];
  income_totals: GroupTotals;
  transfer_rows: PivotRow[];
  transfer_totals: GroupTotals;
  column_totals: Record<string, number>;
  grand_total: number;
}

export interface SavedReportView {
  id?: number;
  name: string;
  filters_json: string;
}

export interface TransactionDetail {
  date: string;
  description: string;
  category_name: string | null;
  category_type: string | null;
  account_name: string | null;
  original_amount: number;
  original_currency: string;
  amount_brl: number;
  amount_usd: number;
  amount_eur: number;
}

export const reportsApi = {
  categoryMonthlyPivot: async (params: {
    start_month: string;
    end_month: string;
    currency?: string;
    account_ids?: string;
    category_ids?: string;
  }): Promise<PivotReport> => {
    const response = await api.get('/reports/category-monthly-pivot', { params });
    return response.data;
  },

  transactionDetails: async (params: {
    start_month: string;
    end_month: string;
    currency?: string;
    account_ids?: string;
    category_ids?: string;
  }): Promise<TransactionDetail[]> => {
    const response = await api.get('/reports/transaction-details', { params });
    return response.data;
  },

  listSavedViews: async (): Promise<SavedReportView[]> => {
    const response = await api.get('/reports/saved-views');
    return response.data;
  },

  createSavedView: async (data: SavedReportView): Promise<SavedReportView> => {
    const response = await api.post('/reports/saved-views', data);
    return response.data;
  },

  updateSavedView: async (id: number, data: SavedReportView): Promise<SavedReportView> => {
    const response = await api.put(`/reports/saved-views/${id}`, data);
    return response.data;
  },

  deleteSavedView: async (id: number): Promise<void> => {
    await api.delete(`/reports/saved-views/${id}`);
  },

  dashboardSummary: async (month?: string): Promise<DashboardSummary> => {
    const response = await api.get('/reports/dashboard-summary', {
      params: month ? { month } : undefined,
    });
    return response.data;
  },
};

// Budget Grid
export interface BudgetGridRow {
  category_id: number;
  category_name: string;
  category_type: string;
  category_color: string | null;
  values: Record<string, number>;
  total: number;
}

export interface BudgetGridResponse {
  months: string[];
  currency: string;
  expense_rows: BudgetGridRow[];
  expense_total: number;
  income_rows: BudgetGridRow[];
  income_total: number;
  transfer_rows: BudgetGridRow[];
  transfer_total: number;
  grand_total: number;
}

export interface BudgetCellUpdateResult {
  ok: boolean;
  action: string;
  amount_brl?: number;
  amount_usd?: number;
  amount_eur?: number;
}

export const budgetsApi = {
  getGrid: async (params: {
    start_month: string;
    end_month: string;
    currency?: string;
  }): Promise<BudgetGridResponse> => {
    const response = await api.get('/budgets/grid', { params });
    return response.data;
  },

  updateCell: async (data: {
    month: string;
    category_id: number;
    amount: number;
    currency: string;
  }): Promise<BudgetCellUpdateResult> => {
    const response = await api.put('/budgets/cell', data);
    return response.data;
  },

  copyMonth: async (sourceMonth: string, targetMonth: string): Promise<{ success: boolean; copied_count: number }> => {
    const response = await api.post('/budgets/copy', {
      source_month: sourceMonth,
      target_month: targetMonth,
    });
    return response.data;
  },
};

export default api;
