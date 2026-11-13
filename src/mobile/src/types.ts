export interface SubcategoryItem {
  id: number;
  name: string;
  category_id: number;
  category_name: string;
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
  amount: number;
  description: string;
  date: string; // YYYY-MM-DD
  subcategory_id: number;
  subcategory_name: string;
  created_at_utc: string;
  status: "PENDING_SYNC" | "SYNCED";
}

export type ActiveTab = "capture" | "history";
