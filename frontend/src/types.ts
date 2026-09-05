export interface Account { username: string; business_name: string; role: string; is_system_admin: boolean }
export interface Dashboard { counts: Record<string, number>; status_counts: Record<string, number>; recent_messages: Record<string, number>; platforms: Record<string, unknown> }
export type AnalyticsWindow = "D" | "W" | "M" | "Y" | "ALL";
export interface AnalyticsUserRow { platform: string; account: string; status: string; total: number; created: number; updated: number }
export interface AnalyticsMessagePoint { day: string; platform: string; count: number }
export interface AnalyticsRoleMessagePoint { day: string; role: string; count: number }
export interface AnalyticsOverview { window: AnalyticsWindow; since?: string; users: AnalyticsUserRow[]; messages: AnalyticsRoleMessagePoint[]; new_users: AnalyticsMessagePoint[] }
export interface Page<T> { items: T[]; page: number; limit: number; total: number }
export interface Product { _id: string; title: string; category?: string; sku?: string; price?: unknown; stock_status?: string; description?: string }
export interface Agent { id: string; title: string; status: string; platform: string; account_id?: string; model: string; instruction: string; vector_store_id?: string }
export interface AgentAccountOption { id: string; platform: string; name?: string; username?: string; status?: string }
export interface AgentOptions { models: string[]; vector_store_ids: string[]; accounts: AgentAccountOption[] }
export interface Knowledge { _id: string; title: string; content: string; content_format: "markdown" | "json" }
export interface Conversation { user_id: string; username?: string; first_name?: string; platform: string; account_username?: string; status: string; updated_at: string; direct_messages?: Array<{ text: string; role: string; timestamp: string }> }
export interface Content { id: string; source_id: string; caption: string; media_url?: string; thumbnail_url?: string; media_type?: string; timestamp?: string; like_count: number; label: string; admin_explanation?: string; fixed_responses: unknown[] }

export interface PlatformAccount {
  id: string;
  name: string;
  username?: string;
  platform?: "instagram" | "telegram" | "bale";
  status: "active" | "inactive";
  modules: Record<string, { enabled: boolean }>;
  webhook_verified?: boolean;
  webhook_url?: string;
  secret_token?: string;
  verify_token?: string;
  ig_id?: string;
  bot_username?: string;
  page_access_token?: string;
  facebook_access_token?: string;
  telegram_access_token?: string;
  bale_access_token?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceSettings {
  username: string;
  business_name?: string;
  email?: string;
  notes?: string;
  platforms: {
    instagram?: { enabled: boolean; accounts?: PlatformAccount[]; modules?: Record<string, { enabled: boolean }> };
    telegram?: { enabled: boolean; accounts?: PlatformAccount[]; modules?: Record<string, { enabled: boolean }> };
    bale?: { enabled: boolean; accounts?: PlatformAccount[]; modules?: Record<string, { enabled: boolean }> };
  };
}
