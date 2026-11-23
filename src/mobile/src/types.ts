export interface SubcategoryItem {
  id: number;
  name: string;
  category_id: number;
  category_name: string;
  category_type?: "expense" | "income";
  is_frequent: boolean;
}

export interface CatalogData {
  device_id: string;
  last_updated_utc: string;
  personal_subcategories: SubcategoryItem[];
  frequent_concepts: string[];
}

export interface MobileTransaction {
  event_id: string;
  scope: "PERSONAL";
  type?: "EXPENSE" | "INCOME";
  amount: number;
  description: string;
  date: string; // YYYY-MM-DD
  subcategory_id: number;
  subcategory_name: string;
  created_at_utc: string;
  status: "PENDING_SYNC" | "SYNCED";
  receipt_base64?: string;
  receipt_filename?: string;
}

export type ActiveTab = "capture" | "search" | "history" | "summary";

export interface MobileCategorySummary {
  category_name: string;
  rule_percentage: number;
  spent: number;
  budget: number;
  remaining: number;
  progress_percentage: number;
}

export interface MobileSubcategorySummary {
  subcategory_id: number;
  subcategory_name: string;
  category_name: string;
  spent: number;
  budget: number;
}

export interface EmergencyFundSummary {
  current_amount: number;
  target_amount: number;
  months_covered: number;
  is_funded: boolean;
}

export interface MobileMonthlySummary {
  month: string;
  total_income: number;
  total_spent: number;
  remaining_budget: number;
  needs: MobileCategorySummary;
  wants: MobileCategorySummary;
  savings: MobileCategorySummary;
  emergency_fund: EmergencyFundSummary;
  subcategories: MobileSubcategorySummary[];
}

export interface MobileVersionInfo {
  version_code: number;
  version_name: string;
  apk_available: boolean;
  apk_url?: string;
  apk_filename?: string;
  apk_size_bytes?: number;
  release_notes?: string;
  released_at_utc?: string;
}

export interface HistoricalTransactionItem {
  id: number;
  date: string;
  amount: number;
  description: string;
  type?: "EXPENSE" | "INCOME";
  subcategory_id: number;
  subcategory_name: string;
  category_name: string;
  receipt_filename?: string;
  receipt_url?: string;
}

export interface SearchResponse {
  query: string;
  total_found: number;
  items: HistoricalTransactionItem[];
}

export interface QuickPresetItem {
  id: string;
  name: string;
  emoji: string;
  amount: number;
  subcategory_id?: number;
  subcategory_name: string;
  concept: string;
}

