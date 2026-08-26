export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type AccountType = "checking" | "savings" | "credit_card" | "other";

export interface Account {
  id: string;
  display_name: string;
  bank_name: string | null;
  account_type: AccountType;
  created_at: string;
}

export interface Statement {
  id: string;
  account_id: string | null;
  original_filename: string;
  file_type: string;
  detected_structure: string | null;
  parse_status: string;
  parse_method: string | null;
  bank_profile_id: string | null;
  bank_profile_match_score: number | null;
  row_count_total: number;
  row_count_parsed: number;
  row_count_failed: number;
  error_message: string | null;
  uploaded_at: string;
}

export type CategorizationMethod =
  | "rule_exact"
  | "rule_fuzzy"
  | "llm"
  | "manual_user_correction"
  | null;

export interface Transaction {
  id: string;
  account_id: string | null;
  raw_merchant: string;
  normalized_merchant: string | null;
  category: string | null;
  categorization_method: CategorizationMethod;
  confidence: string | null;
  amount: string;
  date: string;
  running_balance: string | null;
  row_index: number | null;
  is_split: boolean;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TransactionSplitAllocation {
  category: string;
  amount: string;
}

export interface SpendingByCategory {
  by_category: Record<string, string>;
  total_spend: string;
}

export interface SpendingTrendPoint {
  month: string;
  total_spend: string;
}

export interface TopMerchant {
  merchant: string;
  total_spend: string;
  transaction_count: number;
}

export interface RecurringGroup {
  normalized_merchant: string;
  typical_amount: string;
  frequency_label: string;
  occurrences: number;
  last_date: string;
  next_expected_date: string;
  transaction_ids: string[];
}

export const CATEGORIES = [
  "groceries",
  "dining",
  "food_delivery",
  "transit",
  "utilities",
  "subscriptions",
  "entertainment",
  "shopping",
  "travel",
  "health",
  "income",
  "transfers",
  "fees",
  "other",
] as const;

export type Category = (typeof CATEGORIES)[number];
