import { apiRequest } from "./api";
import type {
  Account,
  AccountType,
  AnomalyDetectRun,
  AnomalyFlag,
  AnomalyStats,
  RecurringGroup,
  SpendingByCategory,
  SpendingTrendPoint,
  Statement,
  TokenPair,
  TopMerchant,
  Transaction,
  TransactionListResponse,
  TransactionSplitAllocation,
  User,
} from "./types";

export function register(email: string, password: string): Promise<User> {
  return apiRequest<User>("/auth/register", {
    method: "POST",
    body: { email, password },
    skipAuth: true,
  });
}

export function login(email: string, password: string): Promise<TokenPair> {
  return apiRequest<TokenPair>("/auth/login", {
    method: "POST",
    body: { email, password },
    skipAuth: true,
  });
}

export function logout(refreshToken: string): Promise<void> {
  return apiRequest<void>("/auth/logout", {
    method: "POST",
    body: { refresh_token: refreshToken },
  });
}

export function getCurrentUser(): Promise<User> {
  return apiRequest<User>("/auth/me");
}

export function listAccounts(): Promise<Account[]> {
  return apiRequest<Account[]>("/accounts");
}

export function createAccount(
  displayName: string,
  bankName: string | null,
  accountType: AccountType,
): Promise<Account> {
  return apiRequest<Account>("/accounts", {
    method: "POST",
    body: { display_name: displayName, bank_name: bankName, account_type: accountType },
  });
}

export function uploadStatement(
  file: File,
  accountId?: string,
  bankHint?: string,
): Promise<Statement> {
  const form = new FormData();
  form.append("file", file);
  if (accountId) form.append("account_id", accountId);
  if (bankHint) form.append("bank_hint", bankHint);
  return apiRequest<Statement>("/statements/upload", { method: "POST", form });
}

export function listStatements(): Promise<Statement[]> {
  return apiRequest<Statement[]>("/statements");
}

export function getStatementTransactions(statementId: string): Promise<Transaction[]> {
  return apiRequest<Transaction[]>(`/statements/${statementId}/transactions`);
}

export interface TransactionListParams {
  account_id?: string;
  category?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export function listTransactions(
  params: TransactionListParams = {},
): Promise<TransactionListResponse> {
  return apiRequest<TransactionListResponse>("/transactions", { params });
}

export function recategorizeTransaction(
  transactionId: string,
  category: string,
): Promise<Transaction> {
  return apiRequest<Transaction>(`/transactions/${transactionId}/category`, {
    method: "PATCH",
    body: { category },
  });
}

export function splitTransaction(
  transactionId: string,
  splits: TransactionSplitAllocation[],
): Promise<Transaction> {
  return apiRequest<Transaction>(`/transactions/${transactionId}/split`, {
    method: "POST",
    body: { splits },
  });
}

export function unsplitTransaction(transactionId: string): Promise<Transaction> {
  return apiRequest<Transaction>(`/transactions/${transactionId}/split`, { method: "DELETE" });
}

export function getTransactionSplits(
  transactionId: string,
): Promise<TransactionSplitAllocation[]> {
  return apiRequest<TransactionSplitAllocation[]>(`/transactions/${transactionId}/splits`);
}

export function getSpendingByCategory(params: {
  account_id?: string;
  start_date?: string;
  end_date?: string;
}): Promise<SpendingByCategory> {
  return apiRequest<SpendingByCategory>("/transactions/spending/by-category", { params });
}

export function getSpendingTrend(
  months: number,
  accountId?: string,
): Promise<SpendingTrendPoint[]> {
  return apiRequest<SpendingTrendPoint[]>("/transactions/spending/trend", {
    params: { months, account_id: accountId },
  });
}

export function getTopMerchants(params: {
  account_id?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<TopMerchant[]> {
  return apiRequest<TopMerchant[]>("/transactions/spending/top-merchants", { params });
}

export function getRecurringTransactions(accountId?: string): Promise<RecurringGroup[]> {
  return apiRequest<RecurringGroup[]>("/transactions/recurring", {
    params: { account_id: accountId },
  });
}

export function listAnomalies(includeDismissed = false): Promise<AnomalyFlag[]> {
  return apiRequest<AnomalyFlag[]>("/anomalies", {
    params: { include_dismissed: includeDismissed },
  });
}

export function runAnomalyDetection(): Promise<AnomalyDetectRun> {
  return apiRequest<AnomalyDetectRun>("/anomalies/detect", { method: "POST" });
}

export function dismissAnomaly(flagId: string, reason?: string): Promise<AnomalyFlag> {
  return apiRequest<AnomalyFlag>(`/anomalies/${flagId}/dismiss`, {
    method: "POST",
    body: { reason: reason ?? null },
  });
}

export function getAnomalyStats(): Promise<AnomalyStats> {
  return apiRequest<AnomalyStats>("/anomalies/stats");
}
