// Tipos base
export interface Bank {
  id: number;
  name: string;
  code: string | null;
  color: string;
  logo_url: string | null;
  created_at: string;
}

export interface BankAccount {
  id: number;
  bank_id: number;
  name: string;
  account_number: string | null;
  account_type: 'checking' | 'savings' | 'credit_card' | 'investment';
  currency: 'BRL' | 'USD' | 'EUR';
  initial_balance: number;
  current_balance: number;
  is_active: boolean;
  created_at: string;
  bank_name?: string;
  balance_brl?: number | null;
}

export interface Category {
  id: number;
  name: string;
  type: 'income' | 'expense' | 'transfer';
  color: string;
  icon: string | null;
  parent_id: number | null;
  is_active: boolean;
  created_at: string;
  children?: Category[];
}

export interface Transaction {
  id: number;
  account_id: number;
  category_id: number | null;
  date: string;
  description: string;
  original_description: string | null;
  amount: number;
  amount_brl: number;
  amount_usd: number;
  amount_eur: number;
  original_currency: 'BRL' | 'USD' | 'EUR';
  original_amount: number;
  balance_after: number | null;
  card_payment_date: string | null;
  transaction_hash: string | null;
  is_validated: boolean;
  import_batch_id: number | null;
  created_at: string;
  account_name?: string;
  category_name?: string;
  category_color?: string;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  balance_before: number | null;
}

export interface CategorizationRule {
  id: number;
  category_id: number;
  pattern: string;
  match_type: 'contains' | 'starts_with' | 'ends_with' | 'exact' | 'regex';
  priority: number;
  is_active: boolean;
  hit_count: number;
  created_at: string;
  category_name?: string;
}

export interface ImportBatch {
  id: number;
  account_id: number;
  filename: string;
  file_type: 'csv' | 'xlsx' | 'pdf';
  total_records: number;
  imported_records: number;
  duplicate_records: number;
  error_records: number;
  status: 'pending' | 'processing' | 'completed' | 'completed_with_duplicates' | 'failed';
  error_message: string | null;
  imported_at: string;
}

// Tipos de resposta da API
export interface ColumnMapping {
  date_column: string;
  description_column: string;
  amount_column: string | null;
  balance_column: string | null;
  bank_column: string | null;
  account_column: string | null;
  // Colunas multi-moeda
  valor_brl_column: string | null;
  valor_usd_column: string | null;
  valor_eur_column: string | null;
  // Colunas adicionais
  category_column: string | null;
  card_payment_date_column: string | null;
}

export interface ImportPreview {
  batch_id: number;
  total_rows: number;
  columns: string[];
  detected_mapping: ColumnMapping;
  preview_rows: Record<string, any>[];
  temp_file_path: string;
  has_template: boolean;
}

export interface ImportResult {
  batch_id: number;
  success: boolean;
  imported_count: number;
  duplicate_count: number;
  error_count: number;
  errors: Array<{ row: number; field: string | null; message: string }>;
  duplicates: Array<{ row: number; date: string; description: string; amount: number; existing_id: number }>;
  balance_validated: boolean;
  balance_matches: boolean;
  balance_difference: number | null;
  installments_detected: number;
  categories_assigned: number;
}

export interface UncertainRow {
  row: number;
  date: string;
  description: string;
  amount: number;
  similar_to_id: number;
  similar_to_description: string;
  similarity: number;
}

export interface TransactionPreviewRow {
  row: number;
  date: string;
  description: string;
  amount: number;
  status: 'new' | 'duplicate' | 'uncertain';
  is_installment: boolean;
  adjusted_date: string | null;
  running_balance: number | null;
  file_balance: number | null;
  balance_ok: boolean | null;
}

export interface ImportAnalysis {
  batch_id: number;
  total_rows: number;
  new_count: number;
  duplicate_count: number;
  fuzzy_duplicate_count: number;
  uncertain_count: number;
  error_count: number;
  date_range_start: string | null;
  date_range_end: string | null;
  overlap_info: string | null;
  uncertain_rows: UncertainRow[];
  // Totais calculados para validação de saldo
  calculated_total: number | null;
  positive_total: number | null;
  negative_total: number | null;
  positive_count: number;
  negative_count: number;
  // Running balance
  running_balance_final: number | null;
  first_balance_divergence_row: number | null;
  transactions_preview: TransactionPreviewRow[];
}

export interface OverlapCheckResponse {
  has_overlap: boolean;
  existing_transaction_count: number;
  overlapping_batches: Array<{ batch_id: number; filename: string; date_start: string; date_end: string }>;
  message: string;
}

export interface TransactionSuggestion {
  transaction_id: number;
  suggested_category_id: number | null;
  suggested_category_name: string | null;
  confidence: number;
  method: string;
}

export interface Projection {
  date: string;
  month: string;
  projected_balance: number;
  expected_change?: number;
  method: string;
}

// Auth
export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Dashboard
export interface DashboardAccountBalance {
  account_id: number;
  account_name: string;
  bank_name: string;
  bank_color: string | null;
  currency: string;
  balance: number;
  balance_brl: number;
  account_type: string;
}

export interface DashboardTopCategory {
  category_id: number;
  category_name: string;
  category_color: string | null;
  amount: number;
  percentage: number;
}

export interface DashboardMonthEvolution {
  month: string;
  income: number;
  expense: number;
  balance: number;
}

export interface DashboardSummary {
  total_balance_brl: number;
  month_income: number;
  month_expenses: number;
  pending_count: number;
  accounts: DashboardAccountBalance[];
  top_categories: DashboardTopCategory[];
  monthly_evolution: DashboardMonthEvolution[];
}
