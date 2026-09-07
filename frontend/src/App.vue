<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { api, ApiError, getCsrfToken, setCsrfToken } from "./api/client";
import type { Account, Agent, AgentOptions, AnalyticsOverview, AnalyticsUserRow, AnalyticsWindow, Content, Conversation, Knowledge, Page, PlatformAccount, Product, WorkspaceSettings } from "./types";
import instagramIcon from "./assets/icons/instagram.png";
import telegramIcon from "./assets/icons/telegram.png";
import baleIcon from "./assets/icons/bale.png";

const platformMeta = {
  instagram: { icon: instagramIcon, name: "Instagram" },
  telegram: { icon: telegramIcon, name: "Telegram" },
  bale: { icon: baleIcon, name: "Bale" },
} as const;

function platformIcon(key: string): string | undefined {
  if (key === "instagram") return platformMeta.instagram.icon;
  if (key === "telegram") return platformMeta.telegram.icon;
  if (key === "bale") return platformMeta.bale.icon;
  return undefined;
}
function statusTagClass(status: string): string {
  const failed = ["INSTAGRAM_FAILED", "TELEGRAM_FAILED", "BALE_FAILED", "ASSISTANT_FAILED"];
  const replied = ["ADMIN_REPLIED", "ASSISTANT_REPLIED", "FIXED_REPLIED"];
  const waiting = "WAITING";
  if (failed.includes(status)) return "tag-platform-failed";
  if (replied.includes(status)) return "tag-platform-replied";
  if (status === waiting) return "tag-platform-waiting";
  return "";
}

type Section = "overview" | "messages" | "instagram" | "knowledge" | "agents" | "catalog" | "settings" | "system";
const account = ref<Account | null>(null);
const section = ref<Section>("overview");
const currentPath = ref(window.location.pathname);
const loading = ref(true);
const actionLoading = ref(false);
const message = ref("");
const error = ref("");
const analyticsWindow = ref<AnalyticsWindow>("M");
const analyticsData = ref<AnalyticsOverview | null>(null);
const analyticsLoading = ref(false);
const chartHover = ref<{ chart: string; index: number } | null>(null);
const windowLabels: Array<[AnalyticsWindow, string]> = [["D", "Day"], ["W", "Week"], ["M", "Month"], ["Y", "Year"], ["ALL", "All"]];
const products = ref<Page<Product> | null>(null);
const agents = ref<Agent[]>([]);
const agentOptions = ref<AgentOptions>({ models: [], vector_store_ids: [], accounts: [] });
const editingAgentId = ref<string | null>(null);
const isAgentFormOpen = ref(false);
interface AgentTestMessage { role: "user" | "assistant"; text?: string; image?: string }
const agentTest = ref<Record<string, { open: boolean; conversation_id: string | null; message: string; image: string | null; messages: AgentTestMessage[]; loading: boolean }>>({});
const knowledge = ref<Page<Knowledge> | null>(null);
const content = ref<Page<Content> | null>(null);
const contentKind = ref<"posts" | "stories">("posts");
const conversations = ref<Page<Conversation> | null>(null);
const selectedConversation = ref<Conversation | null>(null);
const conversationMessages = ref<Array<{ text: string; role: string; timestamp: string }>>([]);
const reply = ref("");
const login = ref({ username: "", password: "" });
const knowledgeDraft = ref({ title: "", content: "", content_format: "markdown" });
const agentDraft = ref({ title: "", instruction: "", model: "", platform: "instagram", account_id: "", status: "active", vector_store_id: "" });
const catalogSearch = ref("");
const systemClients = ref<Array<{ username: string; business_name: string; status: string }>>([]);
const clientDraft = ref({ username: "", business_name: "", password: "", email: "", status: "inactive" });
const credentialDraft = ref({ username: "", telegram_access_token: "", bale_access_token: "", page_access_token: "", facebook_access_token: "" });
const broadcastDraft = ref({ text: "", image_url: "" });
const userStatuses = ["SCRAPED", "WAITING", "ADMIN_REPLIED", "ASSISTANT_REPLIED", "FIXED_REPLIED", "BROADCASTED", "INSTAGRAM_FAILED", "TELEGRAM_FAILED", "BALE_FAILED", "ASSISTANT_FAILED"];
const inboxFilters = ref({ platform: "", account: "", status: "", date_from: "", date_to: "", search: "" });
interface InboxAccount { id: string; name?: string; username?: string; bot_username?: string }
const inboxAccounts = ref<{ instagram: InboxAccount[]; telegram: InboxAccount[]; bale: InboxAccount[] }>({ instagram: [], telegram: [], bale: [] });
// ---- Unified Messages page (merged Inbox + Broadcast) ----
const msgTab = ref<"chats" | "broadcast">("chats");
const broadcastMode = ref<"targeted" | "telegram">("targeted");
const broadcastResult = ref<{ successful: number; failed: number; matched: number } | null>(null);
const audiencePreview = ref<{ total: number; loading: boolean }>({ total: 0, loading: false });
const broadcastProgress = ref<{ active: boolean; current: number; total: number; percent: number; successful: number; failed: number } | null>(null);
const inboxLoading = ref(false);
const inboxLoadingMore = ref(false);
const threadLoading = ref(false);
const replySending = ref(false);
const INBOX_PAGE_SIZE = 25;
const inboxAccountOptions = computed(() => {
  if (!inboxFilters.value.platform) return [...(inboxAccounts.value.instagram || []), ...(inboxAccounts.value.telegram || []), ...(inboxAccounts.value.bale || [])];
  return inboxAccounts.value[inboxFilters.value.platform as "instagram" | "telegram" | "bale"] || [];
});
const activeFilterCount = computed(() => Object.values(inboxFilters.value).filter(Boolean).length);
const broadcastAudienceSummary = computed(() => {
  if (broadcastMode.value === "telegram") return "All Telegram users";
  const parts: string[] = [];
  if (inboxFilters.value.platform) parts.push(inboxFilters.value.platform);
  if (inboxFilters.value.account) parts.push(`@${inboxFilters.value.account}`);
  if (inboxFilters.value.status) parts.push(inboxFilters.value.status.replaceAll("_", " ").toLowerCase());
  if (inboxFilters.value.search) parts.push(`“${inboxFilters.value.search}”`);
  if (inboxFilters.value.date_from || inboxFilters.value.date_to) parts.push(`${inboxFilters.value.date_from || "…"} → ${inboxFilters.value.date_to || "…"}`);
  return parts.length ? parts.join(" · ") : "Everyone (no filters)";
});
const broadcastCharCount = computed(() => broadcastDraft.value.text.length);
const broadcastImageValid = computed(() => {
  const url = broadcastDraft.value.image_url.trim();
  if (!url) return true;
  return url.startsWith("https://");
});
const roleMeta: Record<string, { icon: string; label: string }> = {
  user: { icon: "👤", label: "User" },
  assistant: { icon: "✨", label: "AI Assistant" },
  admin: { icon: "🛡️", label: "Admin" },
  fixed_response: { icon: "📌", label: "Fixed reply" },
  broadcast: { icon: "📢", label: "Broadcast" },
};
function parseTimestamp(value?: string): Date | null {
  if (!value) return null;
  // Backend now emits "Z" but older data / naive ISO without tz was parsed as local -> 3.5h Tehran offset bug.
  // If string looks like "YYYY-MM-DDTHH:mm:ss(.sss)?" without timezone, treat as UTC.
  const naiveIso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/;
  const hasTz = /Z|[+-]\d{2}:\d{2}$/.test(value);
  const normalized = !hasTz && naiveIso.test(value) ? value + "Z" : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}
function formatTime(value?: string) {
  const date = parseTimestamp(value);
  if (!date) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function formatRelativeTime(value?: string) {
  const date = parseTimestamp(value);
  if (!date) return "";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return "just now";
  const sec = Math.floor(diffMs / 1000);
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} day${day === 1 ? "" : "s"} ago`;
  const month = Math.floor(day / 30);
  if (month < 12) return `${month} month${month === 1 ? "" : "s"} ago`;
  const year = Math.floor(month / 12);
  return `${year} year${year === 1 ? "" : "s"} ago`;
}
function inboxQuery(page = 1, limit = INBOX_PAGE_SIZE) {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  for (const [key, value] of Object.entries(inboxFilters.value)) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

// Settings & Multi-account State
const workspaceSettings = ref<WorkspaceSettings | null>(null);
const platformFilter = ref<"all" | "instagram" | "telegram" | "bale">("all");
const isAddAccountOpen = ref(false);
const isEditModulesOpen = ref(false);
const selectedAccountForEdit = ref<PlatformAccount | null>(null);
const testingAccountId = ref<string | null>(null);
const capabilities = ref<{ has_agents: boolean; has_vision_model: boolean } | null>(null);
const hasAgents = computed(() => capabilities.value?.has_agents ?? false);
const hasVisionModel = computed(() => capabilities.value?.has_vision_model ?? false);

async function loadCapabilities() {
  try {
    capabilities.value = await api<{ has_agents: boolean; has_vision_model: boolean }>("/settings/capabilities");
  } catch {
    capabilities.value = { has_agents: false, has_vision_model: false };
  }
}
function canEnableModule(name: string): boolean {
  if (name === "dm_assist" || name === "orderbook") return hasAgents.value;
  if (name === "vision") return hasVisionModel.value;
  return true;
}
function moduleDisabledReason(name: string): string {
  if ((name === "dm_assist" || name === "orderbook") && !hasAgents.value) return "DM AI Assistant & Orderbook require an agent — create one in Agents first.";
  if (name === "vision" && !hasVisionModel.value) return "Vision AI requires a vision model — not found for this client.";
  return "";
}
function isInstagramAccount(acc: PlatformAccount | null): boolean {
  if (!acc) return false;
  const anyAcc = acc as unknown as { platformType?: string; platform?: string };
  return (anyAcc.platformType || anyAcc.platform) === 'instagram';
}

function generateSecretPhrase(): string {
  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let result = "";
  for (let i = 0; i < 20; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

const accountDraft = ref({
  platform: "telegram" as "instagram" | "telegram" | "bale",
  name: "",
  username: "",
  status: "active" as "active" | "inactive",
  telegram_access_token: "",
  bale_access_token: "",
  secret_token: generateSecretPhrase(),
  ig_id: "",
  page_access_token: "",
  facebook_access_token: "",
  verify_token: generateSecretPhrase(),
  set_webhook_now: true,
  modules: {
    fixed_response: { enabled: true },
    dm_assist: { enabled: true },
    comment_assist: { enabled: false },
    vision: { enabled: true },
    orderbook: { enabled: true },
  },
});

const allAccounts = computed<Array<PlatformAccount & { platformType: "instagram" | "telegram" | "bale" }>>(() => {
  if (!workspaceSettings.value?.platforms) return [];
  const list: Array<PlatformAccount & { platformType: "instagram" | "telegram" | "bale" }> = [];
  const igAccounts = workspaceSettings.value.platforms.instagram?.accounts || [];
  const tgAccounts = workspaceSettings.value.platforms.telegram?.accounts || [];
  const baleAccounts = workspaceSettings.value.platforms.bale?.accounts || [];
  
  for (const acc of igAccounts) {
    list.push({ ...acc, platformType: "instagram" });
  }
  for (const acc of tgAccounts) {
    list.push({ ...acc, platformType: "telegram" });
  }
  for (const acc of baleAccounts) {
    list.push({ ...acc, platformType: "bale" });
  }
  return list;
});

const filteredAccounts = computed(() => {
  if (platformFilter.value === "all") return allAccounts.value;
  return allAccounts.value.filter(a => a.platformType === platformFilter.value);
});

const nav = computed(() => [
  ["overview", "Overview"], ["messages", "Messages"], ["instagram", "Instagram"], ["knowledge", "AI & knowledge"],
    ["agents", "Agents"], ["catalog", "Catalog"], ["settings", "Connect"],
  ...(account.value?.is_system_admin ? [["system", "System"]] : []),
] as Array<[Section, string]>);

function setRoute(path: string, replace = false) {
  if (replace) {
    window.history.replaceState({}, "", path);
  } else if (window.location.pathname !== path) {
    window.history.pushState({}, "", path);
  }
  currentPath.value = path;
}

function notify(text: string) { message.value = text; error.value = ""; window.setTimeout(() => (message.value = ""), 5000); }
function fail(value: unknown) { error.value = value instanceof Error ? value.message : "Something went wrong."; message.value = ""; }
const analyticsPlatform = ref<"" | "instagram" | "telegram" | "bale">("");
const analyticsAccount = ref("");
const analyticsFetchedAt = ref<number | null>(null);
const PLATFORM_COLORS: Record<string, string> = { instagram: "#ff8ad8", telegram: "#76c5ff", bale: "#00d084", unknown: "#94a5c6" };
function platformColor(key: string) {
  return PLATFORM_COLORS[key] || PLATFORM_COLORS.unknown;
}
const analyticsAccountOptions = computed(() => {
  const list = !analyticsPlatform.value
    ? [...(inboxAccounts.value.instagram || []), ...(inboxAccounts.value.telegram || []), ...(inboxAccounts.value.bale || [])]
    : inboxAccounts.value[analyticsPlatform.value] || [];
  return list.filter((acc) => acc.username || acc.bot_username);
});
// ---- Overview scope (single control bar, same /analytics API) ----
const ovWindowLabel = computed(() => windowLabels.find(([id]) => id === analyticsWindow.value)?.[1] || analyticsWindow.value);
function ovAccountLabel(value: string) {
  if (!value) return "";
  const clean = value.replace(/^@/, "");
  const found = [...(inboxAccounts.value.instagram || []), ...(inboxAccounts.value.telegram || []), ...(inboxAccounts.value.bale || [])]
    .find((a) => (a.username || a.bot_username || "") === clean);
  return `@${clean}${found?.name ? ` · ${found.name}` : ""}`;
}
const ovActiveFilterCount = computed(() =>
  (analyticsPlatform.value ? 1 : 0) + (analyticsAccount.value ? 1 : 0) + (analyticsWindow.value !== "M" ? 1 : 0),
);
const ovScopeLabel = computed(() => {
  const parts: string[] = [];
  parts.push(analyticsPlatform.value ? platformMeta[analyticsPlatform.value].name : "All platforms");
  parts.push(analyticsAccount.value ? ovAccountLabel(analyticsAccount.value) : "All accounts");
  parts.push(ovWindowLabel.value);
  return parts.join(" · ");
});
function onAnalyticsPlatformChange() {
  analyticsAccount.value = "";
  loadAnalytics();
}
function resetOverviewFilters() {
  analyticsPlatform.value = "";
  analyticsAccount.value = "";
  if (analyticsWindow.value !== "M") {
    analyticsWindow.value = "M";
    loadAnalytics();
  } else {
    loadAnalytics();
  }
}
async function loadOverview() {
  await Promise.all([loadAnalytics(), loadInboxAccounts()]);
}
async function loadAnalytics() {
  analyticsLoading.value = true;
  chartHover.value = null;
  try {
    const params = new URLSearchParams({ window: analyticsWindow.value });
    if (analyticsPlatform.value) params.set("platform", analyticsPlatform.value);
    if (analyticsAccount.value) params.set("account", analyticsAccount.value);
    analyticsData.value = await api<AnalyticsOverview>(`/analytics?${params}`);
    analyticsFetchedAt.value = Date.now();
  } catch (value) {
    fail(value);
  } finally {
    analyticsLoading.value = false;
  }
}
function setAnalyticsWindow(window: AnalyticsWindow) {
  analyticsWindow.value = window;
  loadAnalytics();
}

interface HistChart { days: string[]; platforms: string[]; data: Record<string, number[]>; max: number; totals: number[] }
function buildHist(points: Array<{ day: string; platform: string; count: number }>, order?: string[]): HistChart {
  const days = [...new Set(points.map((p) => p.day))].sort();
  const present = new Set(points.map((p) => p.platform));
  const platforms = order
    ? [...order.filter((key) => present.has(key)), ...[...present].filter((key) => !order.includes(key))]
    : [...present];
  const data: Record<string, number[]> = {};
  for (const platform of platforms) {
    const lookup = new Map(points.filter((p) => p.platform === platform).map((p) => [p.day, p.count]));
    data[platform] = days.map((day) => lookup.get(day) || 0);
  }
  const totals = days.map((_, i) => platforms.reduce((sum, p) => sum + (data[p][i] || 0), 0));
  return { days, platforms, data, totals, max: Math.max(1, ...totals) };
}
// Message roles come from app/models/enums.py (MessageRole); bottom-to-top stack order
const ROLE_STACK_ORDER = ["user", "assistant", "admin", "fixed_response", "broadcast"];
const ROLE_COLORS: Record<string, string> = {
  user: "#5b8cff",
  assistant: "#a78bfa",
  admin: "#34d399",
  fixed_response: "#fbbf24",
  broadcast: "#f472b6",
  unknown: "#94a5c6",
};
const messagesChart = computed(() => buildHist((analyticsData.value?.messages || []).map((m) => ({ day: m.day, platform: m.role || "unknown", count: m.count })), ROLE_STACK_ORDER));
const newUsersChart = computed(() => buildHist(analyticsData.value?.new_users || []));

// ---- Redesigned "Messages by role" histogram state ----
const msgMode = ref<"count" | "share">("count");
const msgHiddenRoles = ref<string[]>([]);
function toggleMsgRole(role: string) {
  msgHiddenRoles.value = msgHiddenRoles.value.includes(role)
    ? msgHiddenRoles.value.filter((r) => r !== role)
    : [...msgHiddenRoles.value, role];
}
function msgRoleColor(role: string) {
  return ROLE_COLORS[role] || ROLE_COLORS.unknown;
}
const msgAllRoles = computed(() => messagesChart.value.platforms);
const msgVisibleRoles = computed(() => msgAllRoles.value.filter((r) => !msgHiddenRoles.value.includes(r)));
const msgTotalsByRole = computed(() => {
  const totals: Record<string, number> = {};
  for (const role of msgAllRoles.value) {
    totals[role] = (messagesChart.value.data[role] || []).reduce((sum, v) => sum + v, 0);
  }
  return totals;
});
const msgGrandTotal = computed(() => Object.values(msgTotalsByRole.value).reduce((sum, v) => sum + v, 0));
const msgVisibleTotals = computed(() =>
  messagesChart.value.days.map((_, i) => msgVisibleRoles.value.reduce((sum, r) => sum + (messagesChart.value.data[r]?.[i] || 0), 0)),
);
const msgVisibleMax = computed(() => Math.max(1, ...msgVisibleTotals.value));
function niceCeil(value: number) {
  if (value <= 4) return 4;
  const exp = Math.floor(Math.log10(value));
  const base = 10 ** exp;
  const norm = value / base;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return nice * base;
}
const msgNiceMax = computed(() => niceCeil(msgVisibleMax.value));
const msgTicks = computed(() => {
  if (msgMode.value === "share") return [100, 75, 50, 25];
  return [msgNiceMax.value, (msgNiceMax.value * 0.75), (msgNiceMax.value * 0.5), (msgNiceMax.value * 0.25)].map((v) =>
    msgNiceMax.value >= 100 ? Math.round(v) : Math.round(v * 10) / 10,
  );
});
const msgPeak = computed(() => {
  let index = -1, total = 0;
  msgVisibleTotals.value.forEach((t, i) => { if (t > total) { total = t; index = i; } });
  return index < 0 ? null : { index, total, day: messagesChart.value.days[index] };
});
const msgDailyAvg = computed(() => {
  const n = messagesChart.value.days.length;
  if (!n) return 0;
  return msgGrandTotal.value / n;
});
const msgRangeText = computed(() => {
  const days = messagesChart.value.days;
  if (!days.length) return "";
  if (days.length === 1) return fullDate(days[0]);
  return `${shortDay(days[0])} – ${shortDay(days[days.length - 1])} · ${days.length} days`;
});
const msgTrend = computed(() => {
  const totals = msgVisibleTotals.value;
  if (totals.length < 4) return null;
  const mid = Math.floor(totals.length / 2);
  const first = totals.slice(0, mid).reduce((s, v) => s + v, 0) || 1;
  const second = totals.slice(mid).reduce((s, v) => s + v, 0);
  return Math.round(((second - first) / first) * 100);
});
function msgRolePct(role: string) {
  if (!msgGrandTotal.value) return 0;
  return ((msgTotalsByRole.value[role] || 0) / msgGrandTotal.value) * 100;
}
function msgSegHeight(role: string, i: number) {
  const count = messagesChart.value.data[role]?.[i] || 0;
  if (!count) return 0;
  if (msgMode.value === "share") {
    const total = msgVisibleTotals.value[i] || 1;
    return (count / total) * 100;
  }
  return (count / msgNiceMax.value) * 100;
}
function msgTopRole(i: number) {
  for (let k = msgVisibleRoles.value.length - 1; k >= 0; k--) {
    if ((messagesChart.value.data[msgVisibleRoles.value[k]]?.[i] || 0) > 0) return msgVisibleRoles.value[k];
  }
  return "";
}
function isMsgActive(i: number) {
  return chartHover.value?.chart === "messages" && chartHover.value.index === i;
}
function parseDayUtc(day: string): Date | null {
  // Day buckets from backend are "YYYY-MM-DD" in UTC (or Asia/Tehran after fix). Parse as UTC midnight.
  const d = day.includes("T") ? parseTimestamp(day) : new Date(day + "T00:00:00Z");
  return d && !Number.isNaN(d.getTime()) ? d : null;
}
function fullDate(day: string) {
  const date = parseDayUtc(day);
  if (!date) return day;
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function showDayLabel(days: string[], i: number) {
  const step = Math.max(1, Math.ceil(days.length / 8));
  return i % step === 0 || i === days.length - 1;
}
function shortDay(day: string) {
  const date = parseDayUtc(day);
  return !date ? day : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---- Overview dashboard (KPIs, histogram, status pies) ----
// Failed statuses come from app/models/enums.py (UserStatus.*_FAILED)
const FAILED_STATUSES = new Set(["INSTAGRAM_FAILED", "TELEGRAM_FAILED", "BALE_FAILED", "ASSISTANT_FAILED"]);
const PIE_OK_COLORS = ["#5b8cff", "#34d399", "#fbbf24", "#a78bfa", "#22d3ee", "#f472b6"];
const PIE_FAIL_COLORS = ["#ef4444", "#dc2626", "#b91c1c"];
interface PieSlice { status: string; count: number; color: string; failed: boolean; path: string }

const overviewStats = computed(() => {
  const rows = analyticsData.value?.users || [];
  const messages = analyticsData.value?.messages || [];
  const totalMessages = messages.reduce((sum, m) => sum + m.count, 0);
  const totalUsers = rows.reduce((sum, r) => sum + r.created, 0);
  const failedUsers = rows.filter((r) => FAILED_STATUSES.has(r.status)).reduce((sum, r) => sum + r.created, 0);
  const replied = rows.filter((r) => !FAILED_STATUSES.has(r.status) && r.status !== "SCRAPED").reduce((sum, r) => sum + r.created, 0);
  const engagementRate = totalUsers ? (replied / totalUsers) * 100 : 0;
  const failRate = totalUsers ? (failedUsers / totalUsers) * 100 : 0;
  const days = messagesChart.value.days.length || newUsersChart.value.days.length || 0;
  const perDay = days ? totalMessages / days : totalMessages;
  return { totalMessages, totalUsers, failedUsers, replied, engagementRate, failRate, perDay };
});

// ---- Minimal status lists for two pies (Total vs New in window) ----
function buildStatusPie(field: "total" | "created") {
  const totals = new Map<string, number>();
  for (const row of analyticsData.value?.users || []) {
    const v = (row as unknown as Record<string, number>)[field] ?? 0;
    totals.set(row.status, (totals.get(row.status) || 0) + v);
  }
  // Filter out zero-count statuses so empty windows don't show stale slices
  const entries = [...totals.entries()].filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  // Return total=0 when empty so template can show "No users yet" instead of a fake 1-row pie
  if (!entries.length) return { slices: [] as PieSlice[], total: 0 };
  let okIndex = 0, failIndex = 0, angle = -Math.PI / 2;
  const slices: PieSlice[] = [];
  const R = 80, r = 52, C = 100;
  const denom = total || 1;
  entries.forEach(([status, count]) => {
    const failed = FAILED_STATUSES.has(status);
    const color = failed ? PIE_FAIL_COLORS[failIndex++ % PIE_FAIL_COLORS.length] : PIE_OK_COLORS[okIndex++ % PIE_OK_COLORS.length];
    const span = (count / denom) * Math.PI * 2;
    const large = span > Math.PI ? 1 : 0;
    const x1 = C + R * Math.cos(angle), y1 = C + R * Math.sin(angle);
    const x2 = C + R * Math.cos(angle + span), y2 = C + R * Math.sin(angle + span);
    const x3 = C + r * Math.cos(angle + span), y3 = C + r * Math.sin(angle + span);
    const x4 = C + r * Math.cos(angle), y4 = C + r * Math.sin(angle);
    angle += span;
    slices.push({
      status, count, color, failed,
      path: `M${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${large} 1 ${x2.toFixed(2)},${y2.toFixed(2)} L${x3.toFixed(2)},${y3.toFixed(2)} A${r},${r} 0 ${large} 0 ${x4.toFixed(2)},${y4.toFixed(2)} Z`,
    });
  });
  return { slices, total };
}
const statusPieTotal = computed(() => buildStatusPie("total"));
const statusPieNew = computed(() => buildStatusPie("created"));
// Backwards compat: old `statusPie` alias now points to Total
const statusPie = statusPieTotal;
function buildStatusList(pie: { slices: PieSlice[]; total: number }) {
  const total = pie.total || 1;
  return pie.slices.map((s) => ({
    ...s,
    name: s.status.replaceAll("_", " ").toLowerCase(),
    pct: (s.count / total) * 100,
  }));
}
const statusList = computed(() => buildStatusList(statusPieTotal.value));
const statusListTotal = statusList;
const statusListNew = computed(() => buildStatusList(statusPieNew.value));
function buildFailedShare(pie: { slices: PieSlice[]; total: number }) {
  const total = pie.total || 1;
  const failed = pie.slices.filter((s) => s.failed).reduce((sum, s) => sum + s.count, 0);
  return (failed / total) * 100;
}
const failedShare = computed(() => buildFailedShare(statusPieTotal.value));
const failedShareTotal = failedShare;
const failedShareNew = computed(() => buildFailedShare(statusPieNew.value));

// ---- Minimal "New users" chart (same new_users API, shared bar language) ----
const usersHidden = ref<string[]>([]);
function toggleUsersPlatform(platform: string) {
  usersHidden.value = usersHidden.value.includes(platform)
    ? usersHidden.value.filter((p) => p !== platform)
    : [...usersHidden.value, platform];
}
const usersAllPlatforms = computed(() => newUsersChart.value.platforms);
const usersVisiblePlatforms = computed(() => usersAllPlatforms.value.filter((p) => !usersHidden.value.includes(p)));
const usersTotalsByPlatform = computed(() => {
  const totals: Record<string, number> = {};
  for (const p of usersAllPlatforms.value) {
    totals[p] = (newUsersChart.value.data[p] || []).reduce((sum, v) => sum + v, 0);
  }
  return totals;
});
const usersGrandTotal = computed(() => Object.values(usersTotalsByPlatform.value).reduce((sum, v) => sum + v, 0));
const usersVisibleTotals = computed(() =>
  newUsersChart.value.days.map((_, i) => usersVisiblePlatforms.value.reduce((sum, p) => sum + (newUsersChart.value.data[p]?.[i] || 0), 0)),
);
const usersNiceMax = computed(() => niceCeil(Math.max(1, ...usersVisibleTotals.value)));
const usersTicks = computed(() =>
  [usersNiceMax.value, usersNiceMax.value * 0.5].map((v) => (usersNiceMax.value >= 100 ? Math.round(v) : Math.round(v * 10) / 10)),
);
const usersPeak = computed(() => {
  let index = -1, total = 0;
  usersVisibleTotals.value.forEach((t, i) => { if (t > total) { total = t; index = i; } });
  return index < 0 ? null : { index, total, day: newUsersChart.value.days[index] };
});
function usersSegHeight(platform: string, i: number) {
  const count = newUsersChart.value.data[platform]?.[i] || 0;
  if (!count) return 0;
  return (count / usersNiceMax.value) * 100;
}
function usersTopPlatform(i: number) {
  for (let k = usersVisiblePlatforms.value.length - 1; k >= 0; k--) {
    if ((newUsersChart.value.data[usersVisiblePlatforms.value[k]]?.[i] || 0) > 0) return usersVisiblePlatforms.value[k];
  }
  return "";
}
function isUsersActive(i: number) {
  return chartHover.value?.chart === "users" && chartHover.value.index === i;
}
function usersPlatformPct(platform: string) {
  if (!usersGrandTotal.value) return 0;
  return ((usersTotalsByPlatform.value[platform] || 0) / usersGrandTotal.value) * 100;
}
function fmtInt(value: number) {
  return Math.round(value).toLocaleString();
}

async function loadProducts() { products.value = await api<Page<Product>>(`/products?limit=25&search=${encodeURIComponent(catalogSearch.value)}`); }
async function loadKnowledge() { knowledge.value = await api<Page<Knowledge>>("/knowledge?limit=25"); }
async function loadAgents() {
  const [list, options] = await Promise.all([api<Agent[]>("/agents"), api<AgentOptions>("/agents/options")]);
  agents.value = list;
  agentOptions.value = options;
  if (!agentDraft.value.model && options.models.length) agentDraft.value.model = options.models[0];
}
function accountLabel(accountId?: string) {
  if (!accountId) return "All accounts";
  const acc = agentOptions.value.accounts.find((item) => item.id === accountId);
  return acc ? `${acc.name || acc.username || acc.id}${acc.username ? ` (@${acc.username})` : ""}` : accountId;
}
function accountsForPlatform(platform: string) {
  return agentOptions.value.accounts.filter((item) => item.platform === platform);
}
function resetAgentForm() {
  editingAgentId.value = null;
  isAgentFormOpen.value = false;
  agentDraft.value = { title: "", instruction: "", model: agentOptions.value.models[0] || "", platform: "instagram", account_id: "", status: "active", vector_store_id: "" };
}
function editAgent(agent: Agent) {
  editingAgentId.value = agent.id;
  isAgentFormOpen.value = true;
  agentDraft.value = {
    title: agent.title, instruction: agent.instruction, model: agent.model,
    platform: agent.platform, account_id: agent.account_id || "",
    status: agent.status, vector_store_id: agent.vector_store_id || "",
  };
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function freshAgentTest() {
  return { open: true, conversation_id: null, message: "", image: null, messages: [] as AgentTestMessage[], loading: false };
}
function toggleAgentTest(agent: Agent) {
  const current = agentTest.value[agent.id];
  agentTest.value[agent.id] = current ? { ...current, open: !current.open } : freshAgentTest();
}
function onAgentTestImage(agent: Agent, event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { fail("Image must be at most 5 MB."); return; }
  const reader = new FileReader();
  reader.onload = () => { agentTest.value[agent.id].image = String(reader.result); };
  reader.readAsDataURL(file);
}
async function runAgentTest(agent: Agent) {
  const state = agentTest.value[agent.id];
  if (!state || state.loading || (!state.message.trim() && !state.image)) return;
  const outgoing: AgentTestMessage = { role: "user", text: state.message.trim() || undefined, image: state.image || undefined };
  state.messages.push(outgoing);
  state.loading = true;
  const text = state.message, image = state.image;
  state.message = ""; state.image = null;
  try {
    const result = await api<{ reply: string; conversation_id: string }>(`/agents/${agent.id}/test`, {
      method: "POST",
      body: JSON.stringify({ message: text, image, conversation_id: state.conversation_id }),
    });
    state.conversation_id = result.conversation_id;
    state.messages.push({ role: "assistant", text: result.reply });
  } catch (value) {
    fail(value);
  } finally {
    state.loading = false;
    await nextTick();
    const box = document.querySelector(`[data-agent-chat="${agent.id}"]`);
    if (box) box.scrollTop = box.scrollHeight;
  }
}
async function loadContent() { content.value = await api<Page<Content>>(`/content/${contentKind.value}?limit=24`); }
async function loadInboxAccounts() { inboxAccounts.value = await api<{ instagram: InboxAccount[]; telegram: InboxAccount[]; bale: InboxAccount[] }>("/settings/accounts"); }
async function loadInbox() {
  inboxLoading.value = true;
  try {
    conversations.value = await api<Page<Conversation>>(`/conversations?${inboxQuery(1)}`);
  } catch (value) { fail(value); } finally { inboxLoading.value = false; }
}
async function loadMoreConversations() {
  if (!conversations.value || inboxLoadingMore.value) return;
  if (conversations.value.items.length >= conversations.value.total) return;
  inboxLoadingMore.value = true;
  try {
    const nextPage = (conversations.value.page || 1) + 1;
    const more = await api<Page<Conversation>>(`/conversations?${inboxQuery(nextPage)}`);
    conversations.value = { ...more, items: [...conversations.value.items, ...more.items] };
  } catch (value) { fail(value); } finally { inboxLoadingMore.value = false; }
}
function applyInboxFilters() { loadInbox(); previewAudience(); }
function resetInboxFilters() { inboxFilters.value = { platform: "", account: "", status: "", date_from: "", date_to: "", search: "" }; loadInbox(); previewAudience(); }
let searchDebounce: ReturnType<typeof setTimeout> | null = null;
function onSearchInput() {
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => { applyInboxFilters(); }, 450);
}
function clearSearch() { inboxFilters.value.search = ""; applyInboxFilters(); }
async function previewAudience() {
  if (broadcastMode.value === "telegram") return;
  audiencePreview.value.loading = true;
  try {
    const preview = await api<Page<Conversation>>(`/conversations?${inboxQuery(1, 1)}`);
    audiencePreview.value.total = preview.total;
  } catch { /* preview is best-effort */ } finally { audiencePreview.value.loading = false; }
}
async function loadSettings() {
  const [ws, caps, agentsList] = await Promise.all([
    api<WorkspaceSettings>("/settings/workspace"),
    api<{ has_agents: boolean; has_vision_model: boolean }>("/settings/capabilities").catch(() => ({ has_agents: false, has_vision_model: false })),
    api<Agent[]>("/agents").catch(() => []),
  ]);
  workspaceSettings.value = ws;
  capabilities.value = caps;
  agents.value = agentsList;
}

async function changeSection(next: Section) {
  section.value = next; selectedConversation.value = null; error.value = "";
  try {
    if (next === "overview") await loadOverview();
    if (next === "catalog") await loadProducts();
    if (next === "knowledge") await loadKnowledge();
    if (next === "agents") await loadAgents();
    if (next === "instagram") await loadContent();
    if (next === "messages") { await Promise.all([loadInbox(), loadInboxAccounts()]); previewAudience(); }
    if (next === "settings") await loadSettings();
    if (next === "system") systemClients.value = (await api<Page<{ username: string; business_name: string; status: string }>>("/system/clients?limit=50")).items;
  } catch (value) { fail(value); }
}

async function signIn() {
  loading.value = true;
  error.value = "";
  try {
    const result = await api<{ account: Account; csrf_token: string }>("/auth/login", { method: "POST", body: JSON.stringify(login.value) });
    account.value = result.account;
    setCsrfToken(result.csrf_token);
    setRoute("/", false);
    await changeSection("overview");
  } catch (value) {
    fail(value);
  } finally {
    loading.value = false;
  }
}

async function signOut() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (value) {
    // ignore
  } finally {
    account.value = null;
    setRoute("/login", false);
  }
}

async function openAddAccountModal() {
  await loadCapabilities();
  // Ensure agents are also fresh for prerequisite check
  try { agents.value = await api<Agent[]>("/agents"); } catch {}
  const canDM = hasAgents.value;
  const canVision = hasVisionModel.value;
  accountDraft.value = {
    platform: "telegram",
    name: "",
    username: "",
    status: "active",
    telegram_access_token: "",
    bale_access_token: "",
    secret_token: generateSecretPhrase(),
    ig_id: "",
    page_access_token: "",
    facebook_access_token: "",
    verify_token: generateSecretPhrase(),
    set_webhook_now: true,
    modules: {
      fixed_response: { enabled: true },
      dm_assist: { enabled: canDM },
      comment_assist: { enabled: false },
      vision: { enabled: canVision },
      orderbook: { enabled: canDM },
    },
  };
  isAddAccountOpen.value = true;
}

async function createAccount() {
  // Pre-submit guard matching backend prerequisites
  if ((accountDraft.value.modules.dm_assist.enabled || accountDraft.value.modules.orderbook.enabled) && !hasAgents.value) {
    fail("DM AI Assistant & Orderbook require an agent — create one in Agents first.");
    return;
  }
  if (accountDraft.value.modules.vision.enabled && !hasVisionModel.value) {
    fail("Vision AI requires a vision model — not found for this client.");
    return;
  }
  actionLoading.value = true;
  error.value = "";
  try {
    const isTelegram = accountDraft.value.platform === "telegram";
    const isBale = accountDraft.value.platform === "bale";
    const isBotPlatform = isTelegram || isBale;
    const payload = {
      platform: accountDraft.value.platform,
      name: accountDraft.value.name,
      status: accountDraft.value.status,
      modules: accountDraft.value.modules,
      set_webhook_now: isBotPlatform ? true : accountDraft.value.set_webhook_now,
      ...(isTelegram
        ? { telegram_access_token: accountDraft.value.telegram_access_token || undefined, secret_token: accountDraft.value.secret_token || undefined }
        : isBale
          ? { bale_access_token: accountDraft.value.bale_access_token || undefined, secret_token: accountDraft.value.secret_token || undefined }
          : {
              username: accountDraft.value.username || undefined,
              ig_id: accountDraft.value.ig_id || undefined,
              page_access_token: accountDraft.value.page_access_token || undefined,
              facebook_access_token: accountDraft.value.facebook_access_token || undefined,
              verify_token: accountDraft.value.verify_token || undefined,
            }),
    };
    await api("/settings/accounts", { method: "POST", body: JSON.stringify(payload) });
    await loadSettings();
    isAddAccountOpen.value = false;
    notify(`${accountDraft.value.name || "Account"} connected successfully!`);
  } catch (value) {
    fail(value);
  } finally {
    actionLoading.value = false;
  }
}

async function openEditModules(acc: PlatformAccount) {
  await loadCapabilities();
  try { agents.value = await api<Agent[]>("/agents"); } catch {}
  selectedAccountForEdit.value = JSON.parse(JSON.stringify(acc));
  // Force-disable modules that lack prerequisites (so UI reflects reality)
  if (selectedAccountForEdit.value) {
    if (!hasAgents.value) {
      if (selectedAccountForEdit.value.modules.dm_assist) selectedAccountForEdit.value.modules.dm_assist.enabled = false;
      if (selectedAccountForEdit.value.modules.orderbook) selectedAccountForEdit.value.modules.orderbook.enabled = false;
    }
    if (!hasVisionModel.value && selectedAccountForEdit.value.modules.vision) {
      selectedAccountForEdit.value.modules.vision.enabled = false;
    }
  }
  isEditModulesOpen.value = true;
}

async function saveAccountModules() {
  if (!selectedAccountForEdit.value) return;
  if ((selectedAccountForEdit.value.modules.dm_assist?.enabled || selectedAccountForEdit.value.modules.orderbook?.enabled) && !hasAgents.value) {
    fail("DM AI Assistant & Orderbook require an agent — create one in Agents first.");
    return;
  }
  if (selectedAccountForEdit.value.modules.vision?.enabled && !hasVisionModel.value) {
    fail("Vision AI requires a vision model — not found for this client.");
    return;
  }
  actionLoading.value = true;
  try {
    const isBaleOrTelegram = !isInstagramAccount(selectedAccountForEdit.value);
    const acc = selectedAccountForEdit.value as PlatformAccount;
    const payload: Record<string, unknown> = {
      name: acc.name,
      status: acc.status,
      modules: acc.modules,
    };
    // For Bale/Telegram, username is webhook-driven — do not send
    if (!isBaleOrTelegram) payload.username = acc.username;
    await api(`/settings/accounts/${encodeURIComponent(selectedAccountForEdit.value.id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    await loadSettings();
    isEditModulesOpen.value = false;
    notify("Account configuration saved.");
  } catch (value) {
    fail(value);
  } finally {
    actionLoading.value = false;
  }
}

async function triggerSetWebhook(acc: PlatformAccount) {
  testingAccountId.value = acc.id;
  try {
    const res = await api<{ success: boolean; message: string; bot?: { username?: string } }>(
      `/settings/accounts/${encodeURIComponent(acc.id)}/set-webhook`,
      { method: "POST" }
    );
    await loadSettings();
    const botName = res.bot?.username ? ` (@${res.bot.username})` : "";
    notify(`${res.message}${botName}`);
  } catch (value) {
    fail(value);
  } finally {
    testingAccountId.value = null;
  }
}

async function deleteAccount(acc: PlatformAccount) {
  if (!confirm(`Are you sure you want to remove account "${acc.name}"?`)) return;
  try {
    await api(`/settings/accounts/${encodeURIComponent(acc.id)}`, { method: "DELETE" });
    await loadSettings();
    notify(`Account "${acc.name}" removed.`);
  } catch (value) {
    fail(value);
  }
}

function copyToClipboard(text?: string) {
  if (!text) return;
  navigator.clipboard.writeText(text);
  notify("Copied to clipboard!");
}

async function saveKnowledge() {
  try { await api("/knowledge", { method: "POST", body: JSON.stringify(knowledgeDraft.value) }); knowledgeDraft.value = { title: "", content: "", content_format: "markdown" }; await loadKnowledge(); notify("Knowledge entry saved."); } catch (value) { fail(value); }
}
async function removeKnowledge(id: string) { try { await api(`/knowledge/${id}`, { method: "DELETE" }); await loadKnowledge(); notify("Knowledge entry removed."); } catch (value) { fail(value); } }
async function saveAgent() {
  try {
    const payload = { ...agentDraft.value, account_id: agentDraft.value.account_id || null, vector_store_id: agentDraft.value.vector_store_id || null };
    if (editingAgentId.value) {
      await api(`/agents/${editingAgentId.value}`, { method: "PATCH", body: JSON.stringify(payload) });
    } else {
      await api("/agents", { method: "POST", body: JSON.stringify(payload) });
    }
    resetAgentForm();
    await loadAgents();
    notify("Agent saved.");
  } catch (value) { fail(value); }
}
async function removeAgent(id: string) { try { await api(`/agents/${id}`, { method: "DELETE" }); await loadAgents(); notify("Agent removed."); } catch (value) { fail(value); } }
async function chooseConversation(item: Conversation) {
  threadLoading.value = true;
  try { selectedConversation.value = item; conversationMessages.value = await api(`/conversations/${encodeURIComponent(item.user_id)}/messages?platform=${encodeURIComponent(item.platform)}${item.account_username ? `&account=${encodeURIComponent(item.account_username)}` : ""}`); await nextTick(); const box = document.querySelector("[data-thread-scroll]"); if (box) box.scrollTop = box.scrollHeight; } catch (value) { fail(value); } finally { threadLoading.value = false; }
}
async function sendReply() {
  if (!selectedConversation.value || !reply.value.trim() || replySending.value) return;
  if (reply.value.trim().length > 4000) { fail("Reply must be at most 4,000 characters."); return; }
  const selected = selectedConversation.value;
  replySending.value = true;
  try { const sent = await api<{ text: string; role: string; timestamp: string }>(`/conversations/${encodeURIComponent(selected.user_id)}/messages?platform=${encodeURIComponent(selected.platform)}${selected.account_username ? `&account=${encodeURIComponent(selected.account_username)}` : ""}`, { method: "POST", body: JSON.stringify({ text: reply.value.trim() }) }); conversationMessages.value.push(sent); reply.value = ""; await loadInbox(); notify("Message sent."); await nextTick(); const box = document.querySelector("[data-thread-scroll]"); if (box) box.scrollTop = box.scrollHeight; } catch (value) { fail(value); } finally { replySending.value = false; }
}
async function saveContent(item: Content) {
  try { await api(`/content/${contentKind.value}/${encodeURIComponent(item.source_id)}`, { method: "PATCH", body: JSON.stringify({ label: item.label, admin_explanation: item.admin_explanation }) }); notify("Content updated."); } catch (value) { fail(value); }
}
async function createClient() {
  try {
    await api("/system/clients", { method: "POST", body: JSON.stringify(clientDraft.value) });
    clientDraft.value = { username: "", business_name: "", password: "", email: "", status: "inactive" };
    systemClients.value = (await api<Page<{ username: string; business_name: string; status: string }>>("/system/clients?limit=50")).items;
    notify("Client workspace created.");
  } catch (value) { fail(value); }
}
async function saveCredentials() {
  try {
    const { username, ...credentials } = credentialDraft.value;
    await api(`/system/clients/${encodeURIComponent(username)}/credentials`, { method: "PUT", body: JSON.stringify(credentials) });
    credentialDraft.value = { username: "", telegram_access_token: "", bale_access_token: "", page_access_token: "", facebook_access_token: "" };
    notify("Credentials replaced without exposing stored values.");
  } catch (value) { fail(value); }
}
async function broadcast() {
  const text = broadcastDraft.value.text.trim();
  const imageUrl = broadcastDraft.value.image_url.trim();
  if (!text || text.length > 4000) { fail("Broadcast text is required and must be at most 4,000 characters."); return; }
  if (imageUrl && !imageUrl.startsWith("https://")) { fail("Broadcast images must use an HTTPS URL."); return; }
  actionLoading.value = true;
  broadcastResult.value = null;
  broadcastProgress.value = { active: true, current: 0, total: 0, percent: 0, successful: 0, failed: 0 };

  // Helper: consume NDJSON stream and drive broadcastProgress + final result
  async function consumeStream(response: Response): Promise<{ successful: number; failed: number; matched: number }> {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new ApiError(payload.error?.message ?? "Broadcast failed.", response.status);
    }
    // If server returns plain JSON (fallback non-stream endpoint), handle it directly
    const ct = response.headers.get("content-type") || "";
    if (ct.includes("application/json") && !ct.includes("ndjson")) {
      const payload = await response.json().catch(() => ({}));
      const data = payload.data ?? payload;
      return {
        successful: data.successful ?? 0,
        failed: data.failed ?? 0,
        matched: data.matched ?? data.total_users ?? data.total ?? 0,
      };
    }
    const reader = response.body?.getReader();
    if (!reader) {
      const payload = await response.json().catch(() => ({}));
      const data = payload.data ?? payload;
      return { successful: data.successful ?? 0, failed: data.failed ?? 0, matched: data.matched ?? data.total ?? 0 };
    }
    const decoder = new TextDecoder();
    let buffer = "";
    let final: { successful: number; failed: number; matched: number } | null = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          if (evt.type === "start") {
            broadcastProgress.value = { active: true, current: 0, total: evt.total ?? evt.matched ?? 0, percent: 0, successful: 0, failed: 0 };
          } else if (evt.type === "progress") {
            broadcastProgress.value = {
              active: true,
              current: evt.current ?? 0,
              total: evt.total ?? 0,
              percent: evt.percent ?? Math.round(((evt.current ?? 0) / Math.max(1, evt.total ?? 1)) * 100),
              successful: evt.successful ?? 0,
              failed: evt.failed ?? 0,
            };
          } else if (evt.type === "done") {
            final = { successful: evt.successful ?? 0, failed: evt.failed ?? 0, matched: evt.matched ?? evt.total ?? 0 };
            broadcastProgress.value = { active: false, current: evt.matched ?? evt.total ?? 0, total: evt.matched ?? evt.total ?? 0, percent: 100, successful: evt.successful ?? 0, failed: evt.failed ?? 0 };
          } else if (evt.type === "error") {
            throw new Error(evt.message || "Broadcast stream error");
          }
        } catch (e) {
          if (e instanceof ApiError || (e as Error).message?.includes("Broadcast stream error")) throw e;
          // ignore malformed line
        }
      }
    }
    if (buffer.trim()) {
      try {
        const evt = JSON.parse(buffer.trim());
        if (evt.type === "done") final = { successful: evt.successful ?? 0, failed: evt.failed ?? 0, matched: evt.matched ?? evt.total ?? 0 };
      } catch {}
    }
    if (final) return final;
    // Fallback: use last progress as final
    const p = broadcastProgress.value;
    return { successful: p?.successful ?? 0, failed: p?.failed ?? 0, matched: p?.total ?? 0 };
  }

  try {
    if (broadcastMode.value === "telegram") {
      const payload: Record<string, string> = { text };
      if (imageUrl) payload.image_url = imageUrl;
      // Try streaming endpoint first, fallback to legacy JSON if 404
      let resp = await fetch("/api/v1/broadcasts/telegram/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (resp.status === 404) {
        resp = await fetch("/api/v1/broadcasts/telegram", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
          credentials: "include",
          body: JSON.stringify(payload),
        });
      }
      const result = await consumeStream(resp);
      // normalize matched field if service returned total_users
      broadcastResult.value = result;
      notify(`Telegram broadcast: ${result.successful} delivered, ${result.failed} failed out of ${result.matched} recipients.`);
    } else {
      const filters = Object.fromEntries(Object.entries(inboxFilters.value).filter(([, value]) => value));
      const payload: Record<string, unknown> = { text, filters };
      if (imageUrl) payload.image_url = imageUrl;
      let resp = await fetch("/api/v1/broadcasts/custom/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (resp.status === 404) {
        resp = await fetch("/api/v1/broadcasts/custom", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
          credentials: "include",
          body: JSON.stringify(payload),
        });
      }
      const result = await consumeStream(resp);
      broadcastResult.value = result;
      notify(`Broadcast completed: ${result.successful} delivered, ${result.failed} failed out of ${result.matched} matched conversations.`);
    }
    broadcastDraft.value = { text: "", image_url: "" };
    await loadInbox();
  } catch (value) { fail(value); } finally {
    actionLoading.value = false;
    if (broadcastProgress.value) broadcastProgress.value.active = false;
  }
}
async function saveWorkspaceNotes() {
  if (!workspaceSettings.value) return;
  try {
    await api("/settings/workspace", { method: "PATCH", body: JSON.stringify({ notes: workspaceSettings.value.notes }) });
    notify("Workspace notes updated.");
  } catch (value) { fail(value); }
}

onMounted(async () => {
  window.addEventListener("popstate", () => {
    currentPath.value = window.location.pathname;
    if (!account.value && window.location.pathname !== "/login") {
      setRoute("/login", true);
    }
  });

  try {
    const result = await api<{ account: Account; csrf_token: string }>("/auth/me");
    account.value = result.account;
    setCsrfToken(result.csrf_token);
    if (window.location.pathname === "/login") {
      setRoute("/", true);
    }
    await loadOverview();
  } catch (value) {
    account.value = null;
    if (window.location.pathname !== "/login") {
      setRoute("/login", true);
    }
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main v-if="loading" class="center"><div class="spinner" />Loading workspace…</main>
  <main v-else-if="!account || currentPath === '/login'" class="login-page">
    <form class="login-card" @submit.prevent="signIn">
      <span class="eyebrow">COZMOZ CONSOLE</span>
      <h1>Welcome back</h1>
      <p>Sign in with your workspace credentials.</p>
      <label>Username<input v-model="login.username" autocomplete="username" placeholder="e.g. cozmoz_trade_shop" required /></label>
      <label>Password<input v-model="login.password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <button>Sign in</button>
    </form>
  </main>
  <main v-else class="shell">
    <aside><div class="brand">COZMOZ<span>Console</span></div><nav><button v-for="[id, name] in nav" :key="id" :class="{ active: section === id }" @click="changeSection(id)">{{ name }}</button></nav><div class="user"><strong>{{ account.business_name || account.username }}</strong><small>{{ account.is_system_admin ? "System administrator" : "Workspace administrator" }}</small><button class="quiet" @click="signOut">Sign out</button></div></aside>
    <section class="workspace">
      <header>
        <div><span class="eyebrow">{{ section }}</span><h1>{{ nav.find((item) => item[0] === section)?.[1] }}</h1></div>
        <div class="header-actions">
          <button v-if="section === 'instagram'" class="quiet" @click="contentKind = contentKind === 'posts' ? 'stories' : 'posts'; loadContent()">Show {{ contentKind === "posts" ? "stories" : "posts" }}</button>
          <button class="quiet mobile-logout" @click="signOut">Sign out</button>
        </div>
      </header>
      <p v-if="message" class="notice">{{ message }}</p><p v-if="error" class="error">{{ error }}</p>

      <section v-if="section === 'overview'" class="ov">
        <div class="panel ov-bar">
          <div class="ov-scope">
            <label class="ov-field">
              <span>Platform</span>
              <select v-model="analyticsPlatform" :disabled="analyticsLoading" @change="onAnalyticsPlatformChange">
                <option value="">All platforms</option>
                <option value="instagram">Instagram</option>
                <option value="telegram">Telegram</option>
                <option value="bale">Bale</option>
              </select>
            </label>
            <label class="ov-field" :class="{ 'is-disabled': !analyticsAccountOptions.length }">
              <span>Account</span>
              <select v-model="analyticsAccount" :disabled="!analyticsAccountOptions.length || analyticsLoading" @change="loadAnalytics()">
                <option value="">All accounts</option>
                <option v-for="acc in analyticsAccountOptions" :key="acc.id" :value="acc.username || acc.bot_username || ''">
                  {{ acc.name || acc.username || acc.bot_username || acc.id }}<template v-if="acc.username || acc.bot_username"> (@{{ acc.username || acc.bot_username }})</template>
                </option>
              </select>
            </label>
          </div>
          <div class="ov-window" role="tablist" aria-label="Time window">
            <button v-for="[id, label] in windowLabels" :key="id" class="quiet" :class="{ pillActive: analyticsWindow === id }" :disabled="analyticsLoading" @click="setAnalyticsWindow(id)">{{ label }}</button>
          </div>
        </div>
        <p class="ov-context">
          <span v-if="analyticsLoading" class="ov-loading"><span class="ov-pulse" />Updating…</span><span v-else>{{ ovScopeLabel }}<template v-if="msgRangeText"> · {{ msgRangeText }}</template><template v-if="analyticsFetchedAt"> · updated {{ new Date(analyticsFetchedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) }}</template></span>
          <button v-if="ovActiveFilterCount" class="quiet ov-reset" @click="resetOverviewFilters">Reset{{ ovActiveFilterCount > 1 ? ` (${ovActiveFilterCount})` : "" }}</button>
        </p>

        <div class="ov-kpis">
          <article class="panel ov-kpi" :class="{ 'is-loading': analyticsLoading }">
            <span class="ov-kpi-label">Messages</span>
            <strong class="ov-kpi-value">{{ fmtInt(overviewStats.totalMessages) }}</strong>
            <small class="ov-kpi-sub">⌀ {{ overviewStats.perDay >= 10 ? fmtInt(overviewStats.perDay) : overviewStats.perDay.toFixed(1) }} / day</small>
          </article>
          <article class="panel ov-kpi" :class="{ 'is-loading': analyticsLoading }">
            <span class="ov-kpi-label">New users</span>
            <strong class="ov-kpi-value">{{ fmtInt(overviewStats.totalUsers) }}</strong>
            <small class="ov-kpi-sub">created in window</small>
          </article>
          <article class="panel ov-kpi" :class="{ 'is-loading': analyticsLoading }">
            <span class="ov-kpi-label">Engaged</span>
            <strong class="ov-kpi-value">{{ fmtInt(overviewStats.replied) }}</strong>
            <small class="ov-kpi-sub">{{ overviewStats.engagementRate.toFixed(0) }}% of new users</small>
          </article>
          <article class="panel ov-kpi" :class="{ 'is-loading': analyticsLoading, 'is-alert': overviewStats.failedUsers > 0 }">
            <span class="ov-kpi-label">Failed</span>
            <strong class="ov-kpi-value">{{ fmtInt(overviewStats.failedUsers) }}</strong>
            <small class="ov-kpi-sub">{{ overviewStats.failRate.toFixed(1) }}% delivery failure</small>
          </article>
        </div>

        <div class="ov-grid">
          <div class="panel ov-card msg-panel">
            <div class="ov-card-head">
              <div class="ov-card-title">
                <h2>Messages by role</h2>
                <p class="muted ov-card-sub">
                  <template v-if="messagesChart.days.length">
                    <strong>{{ msgGrandTotal.toLocaleString() }}</strong> messages · avg {{ msgDailyAvg >= 10 ? Math.round(msgDailyAvg).toLocaleString() : msgDailyAvg.toFixed(1) }}/day<template v-if="msgPeak"> · peak {{ shortDay(msgPeak.day) }}</template>
                    <span v-if="msgTrend !== null" class="msg-trend" :class="{ up: msgTrend >= 0, down: msgTrend < 0 }">{{ msgTrend >= 0 ? "▲" : "▼" }} {{ Math.abs(msgTrend) }}%</span>
                  </template>
                  <template v-else>{{ analyticsLoading ? "Loading…" : "No data" }}</template>
                </p>
              </div>
              <div class="msg-modes" role="tablist" aria-label="Chart scale">
                <button class="quiet" :class="{ pillActive: msgMode === 'count' }" @click="msgMode = 'count'">Count</button>
                <button class="quiet" :class="{ pillActive: msgMode === 'share' }" @click="msgMode = 'share'">%</button>
              </div>
            </div>

            <div v-if="msgAllRoles.length" class="msg-summary">
              <button
                v-for="role in msgAllRoles" :key="role"
                class="msg-chip"
                :class="{ off: msgHiddenRoles.includes(role) }"
                :aria-pressed="!msgHiddenRoles.includes(role)"
                :title="`Toggle ${roleMeta[role]?.label || role}`"
                @click="toggleMsgRole(role)"
              >
                <i class="msg-chip-dot" :style="{ background: msgRoleColor(role) }" />
                <span class="msg-chip-label">{{ roleMeta[role]?.icon }} {{ roleMeta[role]?.label || role }}</span>
                <strong class="msg-chip-count">{{ (msgTotalsByRole[role] || 0).toLocaleString() }}</strong>
                <small class="msg-chip-pct">{{ msgRolePct(role).toFixed(msgRolePct(role) < 10 && msgRolePct(role) > 0 ? 1 : 0) }}%</small>
                <span class="msg-chip-bar"><span :style="{ width: `${Math.max(2, Math.min(100, msgRolePct(role)))}%`, background: msgRoleColor(role) }" /></span>
              </button>
            </div>

            <div v-if="messagesChart.days.length" class="msg-chart-wrap">
              <div v-if="analyticsLoading" class="msg-skeleton" aria-hidden="true">
                <div v-for="n in 12" :key="n" class="msg-skel-bar" :style="{ height: `${18 + ((n * 37) % 62)}%` }" />
              </div>
              <div v-else class="msg-body">
                <div class="msg-yaxis" aria-hidden="true">
                  <span v-for="tick in msgTicks" :key="tick">{{ msgMode === "share" ? `${tick}%` : tick.toLocaleString() }}</span>
                  <span class="msg-zero">{{ msgMode === "share" ? "0%" : "0" }}</span>
                </div>
                <div class="msg-scroll">
                  <div class="msg-grid" aria-hidden="true">
                    <i v-for="tick in msgTicks" :key="tick" />
                    <i class="base" />
                  </div>
                  <div class="msg-bars">
                    <div
                      v-for="(day, i) in messagesChart.days" :key="day"
                      class="msg-col"
                      tabindex="0"
                      :class="{ active: isMsgActive(i), peak: msgPeak?.index === i, empty: (msgVisibleTotals[i] || 0) === 0 }"
                      @mouseenter="chartHover = { chart: 'messages', index: i }"
                      @mouseleave="chartHover = null"
                      @focus="chartHover = { chart: 'messages', index: i }"
                      @blur="chartHover = null"
                      @click="chartHover = { chart: 'messages', index: i }"
                    >
                      <div class="msg-bar-track">
                        <div class="msg-bar">
                          <template v-for="role in [...msgVisibleRoles].reverse()" :key="role">
                            <div
                              v-if="(messagesChart.data[role]?.[i] || 0) > 0"
                              class="msg-seg"
                              :class="{ top: msgTopRole(i) === role }"
                              :style="{ height: `${msgSegHeight(role, i)}%`, background: msgRoleColor(role) }"
                            />
                          </template>
                          <span v-if="(msgVisibleTotals[i] || 0) === 0" class="msg-empty-dot" />
                        </div>
                        <span v-if="msgPeak?.index === i" class="msg-peak-flag" title="Peak day">◆</span>
                      </div>
                      <span class="msg-day" :class="{ dim: !showDayLabel(messagesChart.days, i) }">{{ shortDay(day) }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="chartHover?.chart === 'messages' && messagesChart.days[chartHover.index]" class="msg-tooltip">
                <div class="msg-tip-head">
                  <strong>{{ fullDate(messagesChart.days[chartHover.index]) }}</strong>
                  <span>{{ (msgVisibleTotals[chartHover.index] || 0).toLocaleString() }} messages{{ msgMode === "share" ? " · 100%" : "" }}</span>
                </div>
                <div v-for="role in [...msgVisibleRoles].reverse()" :key="role" class="msg-tip-row">
                  <span class="msg-tip-left"><i :style="{ background: msgRoleColor(role) }" />{{ roleMeta[role]?.icon }} {{ roleMeta[role]?.label || role }}</span>
                  <span class="msg-tip-bar"><span :style="{ width: `${msgVisibleTotals[chartHover.index] ? ((messagesChart.data[role]?.[chartHover.index] || 0) / msgVisibleTotals[chartHover.index]) * 100 : 0}%`, background: msgRoleColor(role) }" /></span>
                  <b>{{ (messagesChart.data[role]?.[chartHover.index] || 0).toLocaleString() }}</b>
                  <small>{{ msgVisibleTotals[chartHover.index] ? (((messagesChart.data[role]?.[chartHover.index] || 0) / msgVisibleTotals[chartHover.index]) * 100).toFixed(0) : 0 }}%</small>
                </div>
                <p v-if="msgHiddenRoles.length" class="msg-tip-note">{{ msgHiddenRoles.length }} role{{ msgHiddenRoles.length === 1 ? "" : "s" }} hidden — click a chip above to restore.</p>
              </div>
            </div>
            <p v-else class="empty msg-empty">{{ analyticsLoading ? "Loading…" : "No messages in this window. Try a wider time range." }}</p>
            <p class="msg-foot muted">Click a role to filter · hover a bar for detail</p>
          </div>

          <div class="ov-side">
          <!-- Total status distribution (all time, same platform/account filter) -->
          <div class="panel ov-card">
            <div class="ov-card-head">
              <div class="ov-card-title">
                <h2>Status · Total</h2>
                <p class="muted ov-card-sub">All users in scope{{ analyticsPlatform ? ` · ${platformMeta[analyticsPlatform].name}` : "" }}{{ analyticsAccount ? ` · ${ovAccountLabel(analyticsAccount)}` : "" }}</p>
              </div>
              <span class="ov-total">{{ statusPieTotal.total.toLocaleString() }} users</span>
            </div>
            <template v-if="statusPieTotal.slices.length">
              <div class="ov-donut">
                <svg viewBox="0 0 200 200" class="pie-svg">
                  <path v-for="slice in statusPieTotal.slices" :key="slice.status" :d="slice.path" :fill="slice.color" class="pie-slice"><title>{{ slice.status.replaceAll("_", " ") }}: {{ slice.count }}</title></path>
                  <text x="100" y="95" class="pie-total">{{ statusPieTotal.total }}</text>
                  <text x="100" y="114" class="pie-total-label">users</text>
                </svg>
                <ul class="ov-legend">
                  <li v-for="slice in statusListTotal.slice(0, 6)" :key="slice.status" :class="{ failed: slice.failed }">
                    <i :style="{ background: slice.color }" />
                    <span class="ov-legend-name">{{ slice.name }}{{ slice.failed ? " · failed" : "" }}</span>
                    <b>{{ slice.count.toLocaleString() }}</b>
                    <small>{{ slice.pct.toFixed(0) }}%</small>
                  </li>
                </ul>
                <p v-if="statusListTotal.length > 6" class="muted ov-more">+{{ statusListTotal.length - 6 }} more · {{ failedShareTotal.toFixed(0) }}% failed</p>
                <p v-else-if="failedShareTotal > 0" class="muted ov-more">{{ failedShareTotal.toFixed(1) }}% failed deliveries</p>
              </div>
            </template>
            <p v-else class="empty">{{ analyticsLoading ? "Loading…" : "No users yet." }}</p>
          </div>

          <!-- New users status distribution (created in selected window) -->
          <div class="panel ov-card">
            <div class="ov-card-head">
              <div class="ov-card-title">
                <h2>Status · New</h2>
                <p class="muted ov-card-sub">Created in {{ ovWindowLabel }}{{ analyticsPlatform ? ` · ${platformMeta[analyticsPlatform].name}` : "" }}{{ analyticsAccount ? ` · ${ovAccountLabel(analyticsAccount)}` : "" }}</p>
              </div>
              <span class="ov-total">{{ statusPieNew.total.toLocaleString() }} users</span>
            </div>
            <template v-if="statusPieNew.slices.length">
              <div class="ov-donut">
                <svg viewBox="0 0 200 200" class="pie-svg">
                  <path v-for="slice in statusPieNew.slices" :key="slice.status" :d="slice.path" :fill="slice.color" class="pie-slice"><title>{{ slice.status.replaceAll("_", " ") }}: {{ slice.count }}</title></path>
                  <text x="100" y="95" class="pie-total">{{ statusPieNew.total }}</text>
                  <text x="100" y="114" class="pie-total-label">users</text>
                </svg>
                <ul class="ov-legend">
                  <li v-for="slice in statusListNew.slice(0, 6)" :key="slice.status" :class="{ failed: slice.failed }">
                    <i :style="{ background: slice.color }" />
                    <span class="ov-legend-name">{{ slice.name }}{{ slice.failed ? " · failed" : "" }}</span>
                    <b>{{ slice.count.toLocaleString() }}</b>
                    <small>{{ slice.pct.toFixed(0) }}%</small>
                  </li>
                </ul>
                <p v-if="statusListNew.length > 6" class="muted ov-more">+{{ statusListNew.length - 6 }} more · {{ failedShareNew.toFixed(0) }}% failed</p>
                <p v-else-if="failedShareNew > 0" class="muted ov-more">{{ failedShareNew.toFixed(1) }}% failed deliveries</p>
              </div>
            </template>
            <p v-else class="empty">{{ analyticsLoading ? "Loading…" : "No new users in this window." }}</p>
          </div>

          <div class="panel ov-card">
            <div class="ov-card-head">
              <div class="ov-card-title">
                <h2>Growth</h2>
                <p class="muted ov-card-sub">
                  <template v-if="newUsersChart.days.length"><strong>{{ usersGrandTotal.toLocaleString() }}</strong> new users<template v-if="usersPeak"> · peak {{ shortDay(usersPeak.day) }}</template></template>
                  <template v-else>{{ analyticsLoading ? "Loading…" : "No data" }}</template>
                </p>
              </div>
              <div v-if="usersAllPlatforms.length" class="ov-pills">
                <button
                  v-for="platform in usersAllPlatforms" :key="platform"
                  class="quiet ov-pill"
                  :class="{ off: usersHidden.includes(platform) }"
                  :aria-pressed="!usersHidden.includes(platform)"
                  @click="toggleUsersPlatform(platform)"
                >
                  <i :style="{ background: platformColor(platform) }" /><img v-if="platformIcon(platform)" class="tag-icon" :src="platformIcon(platform)" alt="" />{{ platform }}
                </button>
              </div>
            </div>
            <div v-if="newUsersChart.days.length" class="msg-chart-wrap ov-compact">
              <div v-if="analyticsLoading" class="msg-skeleton" aria-hidden="true">
                <div v-for="n in 12" :key="n" class="msg-skel-bar" :style="{ height: `${18 + ((n * 37) % 62)}%` }" />
              </div>
              <div v-else class="msg-body">
                <div class="msg-yaxis" aria-hidden="true">
                  <span v-for="tick in usersTicks" :key="tick">{{ tick.toLocaleString() }}</span>
                  <span class="msg-zero">0</span>
                </div>
                <div class="msg-scroll">
                  <div class="msg-grid" aria-hidden="true">
                    <i v-for="tick in usersTicks" :key="tick" />
                    <i class="base" />
                  </div>
                  <div class="msg-bars">
                    <div
                      v-for="(day, i) in newUsersChart.days" :key="day"
                      class="msg-col"
                      tabindex="0"
                      :class="{ active: isUsersActive(i), peak: usersPeak?.index === i, empty: (usersVisibleTotals[i] || 0) === 0 }"
                      @mouseenter="chartHover = { chart: 'users', index: i }"
                      @mouseleave="chartHover = null"
                      @focus="chartHover = { chart: 'users', index: i }"
                      @blur="chartHover = null"
                      @click="chartHover = { chart: 'users', index: i }"
                    >
                      <div class="msg-bar-track">
                        <div class="msg-bar">
                          <template v-for="platform in [...usersVisiblePlatforms].reverse()" :key="platform">
                            <div
                              v-if="(newUsersChart.data[platform]?.[i] || 0) > 0"
                              class="msg-seg"
                              :class="{ top: usersTopPlatform(i) === platform }"
                              :style="{ height: `${usersSegHeight(platform, i)}%`, background: platformColor(platform) }"
                            />
                          </template>
                          <span v-if="(usersVisibleTotals[i] || 0) === 0" class="msg-empty-dot" />
                        </div>
                        <span v-if="usersPeak?.index === i" class="msg-peak-flag" title="Peak day">◆</span>
                      </div>
                      <span class="msg-day" :class="{ dim: !showDayLabel(newUsersChart.days, i) }">{{ shortDay(day) }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="chartHover?.chart === 'users' && newUsersChart.days[chartHover.index]" class="msg-tooltip">
                <div class="msg-tip-head">
                  <strong>{{ fullDate(newUsersChart.days[chartHover.index]) }}</strong>
                  <span>{{ (usersVisibleTotals[chartHover.index] || 0).toLocaleString() }} users</span>
                </div>
                <div v-for="platform in [...usersVisiblePlatforms].reverse()" :key="platform" class="msg-tip-row">
                  <span class="msg-tip-left"><i :style="{ background: platformColor(platform) }" /><img v-if="platformIcon(platform)" class="tag-icon" :src="platformIcon(platform)" alt="" />{{ platform }}</span>
                  <span class="msg-tip-bar"><span :style="{ width: `${usersVisibleTotals[chartHover.index] ? ((newUsersChart.data[platform]?.[chartHover.index] || 0) / usersVisibleTotals[chartHover.index]) * 100 : 0}%`, background: platformColor(platform) }" /></span>
                  <b>{{ (newUsersChart.data[platform]?.[chartHover.index] || 0).toLocaleString() }}</b>
                  <small>{{ usersVisibleTotals[chartHover.index] ? (((newUsersChart.data[platform]?.[chartHover.index] || 0) / usersVisibleTotals[chartHover.index]) * 100).toFixed(0) : 0 }}%</small>
                </div>
              </div>
            </div>
            <p v-else class="empty">{{ analyticsLoading ? "Loading…" : "No new users in this window." }}</p>
          </div>
          </div>
        </div>
      </section>
      <section v-else-if="section === 'catalog'" class="stack"><form class="toolbar" @submit.prevent="loadProducts"><input v-model="catalogSearch" placeholder="Search name, SKU, or category" /><button>Search</button></form><div class="panel table-wrap"><table><thead><tr><th>Product</th><th>Category</th><th>SKU</th><th>Stock</th></tr></thead><tbody><tr v-for="item in products?.items" :key="item._id"><td><strong>{{ item.title }}</strong></td><td>{{ item.category || "—" }}</td><td>{{ item.sku || "—" }}</td><td><span class="badge">{{ item.stock_status || "Unknown" }}</span></td></tr></tbody></table><p v-if="!products?.items.length" class="empty">No catalog entries match this search.</p></div></section>
      <section v-else-if="section === 'knowledge'" class="two-column"><form class="panel form" @submit.prevent="saveKnowledge"><h2>New knowledge entry</h2><label>Title<input v-model="knowledgeDraft.title" required /></label><label>Format<select v-model="knowledgeDraft.content_format"><option value="markdown">Markdown</option><option value="json">JSON</option></select></label><label>Content<textarea v-model="knowledgeDraft.content" rows="12" required /></label><button>Save entry</button></form><div class="stack"><article v-for="item in knowledge?.items" :key="item._id" class="panel"><div class="row"><h2>{{ item.title }}</h2><button class="danger quiet" @click="removeKnowledge(item._id)">Delete</button></div><pre>{{ item.content }}</pre></article><p v-if="!knowledge?.items.length" class="empty">No knowledge entries yet.</p></div></section>
      <section v-else-if="section === 'agents'" class="stack">
        <div class="row">
          <p class="muted" style="margin: 0;">{{ agents.length }} agent{{ agents.length === 1 ? "" : "s" }} configured</p>
          <button @click="isAgentFormOpen = !isAgentFormOpen">{{ isAgentFormOpen && !editingAgentId ? "Close" : "+ New agent" }}</button>
        </div>
        <form v-if="isAgentFormOpen" class="panel form agent-form" @submit.prevent="saveAgent">
          <div class="row">
            <h2>{{ editingAgentId ? `Edit: ${agentDraft.title || "agent"}` : "New agent" }}</h2>
            <button type="button" class="quiet" @click="resetAgentForm">Close</button>
          </div>
          <div class="agent-form-grid">
            <label>Title<input v-model="agentDraft.title" required /></label>
            <label>Status
              <select v-model="agentDraft.status">
                <option value="active">Active</option>
                <option value="deactive">Inactive</option>
              </select>
            </label>
            <label>Platform
              <select v-model="agentDraft.platform" @change="agentDraft.account_id = ''">
                <option value="instagram">Instagram</option>
                <option value="telegram">Telegram</option>
                <option value="bale">Bale</option>
              </select>
            </label>
            <label>Account
              <select v-model="agentDraft.account_id">
                <option value="">All {{ agentDraft.platform }} accounts</option>
                <option v-for="acc in accountsForPlatform(agentDraft.platform)" :key="acc.id" :value="acc.id">{{ acc.name || acc.username || acc.id }}<template v-if="acc.username"> (@{{ acc.username }})</template></option>
              </select>
            </label>
            <label>Model
              <select v-model="agentDraft.model">
                <option v-for="model in agentOptions.models" :key="model" :value="model">{{ model }}</option>
              </select>
            </label>
            <label>Vector store
              <select v-model="agentDraft.vector_store_id">
                <option value="">None</option>
                <option v-for="vs in agentOptions.vector_store_ids" :key="vs" :value="vs">{{ vs }}</option>
              </select>
            </label>
          </div>
          <label>Instructions<textarea v-model="agentDraft.instruction" rows="4" required /></label>
          <button>{{ editingAgentId ? "Save changes" : "Create agent" }}</button>
        </form>

        <div class="agent-list">
          <article v-for="agent in agents" :key="agent.id" class="agent-card">
            <div class="agent-card-head">
              <div class="agent-card-title">
                <span class="agent-dot" :class="agent.status" />
                <h3>{{ agent.title || "Untitled agent" }}</h3>
              </div>
              <div class="agent-card-actions">
                <button class="quiet" :class="{ active: agentTest[agent.id]?.open }" @click="toggleAgentTest(agent)">✦ Test</button>
                <button class="quiet" @click="editAgent(agent)">Edit</button>
                <button class="danger quiet" @click="removeAgent(agent.id)">Delete</button>
              </div>
            </div>
            <div class="agent-meta">
              <span class="tag" :class="agent.platform"><img v-if="platformIcon(agent.platform)" class="tag-icon" :src="platformIcon(agent.platform)" alt="" />{{ agent.platform }}</span>
              <span class="tag username">{{ accountLabel(agent.account_id) }}</span>
              <span class="tag mono">{{ agent.model }}</span>
              <span v-if="agent.vector_store_id" class="tag mono">{{ agent.vector_store_id }}</span>
            </div>
            <p class="agent-instruction">{{ agent.instruction }}</p>

            <div v-if="agentTest[agent.id]?.open" class="agent-chat">
              <div class="agent-chat-scroll" :data-agent-chat="agent.id">
                <p v-if="!agentTest[agent.id].messages.length" class="empty">Say something to <strong>{{ agent.title || "this agent" }}</strong> — the conversation remembers context.</p>
                <div v-for="(msg, i) in agentTest[agent.id].messages" :key="i" class="bubble-row" :class="msg.role === 'user' ? 'outgoing' : 'incoming'">
                  <span class="bubble-icon">{{ msg.role === "user" ? "👤" : "✨" }}</span>
                  <div class="bubble" :class="msg.role === 'user' ? 'admin' : 'assistant'">
                    <span class="bubble-role">{{ msg.role === "user" ? "You" : agent.title || "Agent" }}</span>
                    <img v-if="msg.image" :src="msg.image" class="agent-chat-img" alt="" />
                    <template v-if="msg.text">{{ msg.text }}</template>
                  </div>
                </div>
                <div v-if="agentTest[agent.id].loading" class="bubble-row incoming">
                  <span class="bubble-icon">✨</span>
                  <div class="bubble assistant typing"><span /><span /><span /></div>
                </div>
              </div>
              <div v-if="agentTest[agent.id].image" class="agent-chat-attachment">
                <img :src="agentTest[agent.id].image ?? ''" alt="" />
                <button class="quiet" @click="agentTest[agent.id].image = null">Remove</button>
              </div>
              <form class="agent-chat-composer" @submit.prevent="runAgentTest(agent)">
                <label class="attach-btn" :title="'Attach image'">
                  📎
                  <input type="file" accept="image/*" hidden @change="onAgentTestImage(agent, $event)" />
                </label>
                <input v-model="agentTest[agent.id].message" placeholder="Message…" @keydown.enter.exact.prevent="runAgentTest(agent)" />
                <button :disabled="agentTest[agent.id].loading || (!agentTest[agent.id].message.trim() && !agentTest[agent.id].image)">Send</button>
              </form>
            </div>
          </article>
          <p v-if="!agents.length" class="empty">No agents configured yet — create one above.</p>
        </div>
      </section>
      <section v-else-if="section === 'instagram'" class="content-grid"><article v-for="item in content?.items" :key="item.id" class="content-card"><img v-if="item.thumbnail_url || item.media_url" :src="item.thumbnail_url || item.media_url" alt="" /><div><span class="badge">{{ item.media_type || "content" }}</span><p>{{ item.caption || "No caption" }}</p><input v-model="item.label" placeholder="Label" /><textarea v-model="item.admin_explanation" placeholder="Internal explanation" rows="3" /><button class="quiet" @click="saveContent(item)">Save</button></div></article><p v-if="!content?.items.length" class="empty">No {{ contentKind }} have been imported yet.</p></section>
      <section v-else-if="section === 'messages'" class="msg-page">
        <div class="panel msg-tabbar">
          <div class="msg-seg" role="tablist" aria-label="Messages views">
            <button role="tab" :class="{ active: msgTab === 'chats' }" :aria-selected="msgTab === 'chats'" @click="msgTab = 'chats'">💬 Chats<span v-if="conversations" class="msg-count">{{ conversations.total }}</span></button>
            <button role="tab" :class="{ active: msgTab === 'broadcast' }" :aria-selected="msgTab === 'broadcast'" @click="msgTab = 'broadcast'; previewAudience()">📢 Broadcast</button>
          </div>
          <p class="muted msg-tabbar-hint">
            <template v-if="msgTab === 'chats'">All conversations<template v-if="conversations"> · {{ conversations.items.length }} of {{ conversations.total }}</template><template v-if="activeFilterCount"> · {{ activeFilterCount }} filter{{ activeFilterCount === 1 ? "" : "s" }} on</template></template>
            <template v-else>Audience: {{ broadcastAudienceSummary }}<template v-if="broadcastMode === 'targeted'"> · <span v-if="audiencePreview.loading">counting…</span><span v-else>~{{ audiencePreview.total }} matched</span></template></template>
          </p>
        </div>

        <!-- ── Chats (full inbox: GET /conversations + thread + reply) ── -->
        <div v-if="msgTab === 'chats'" class="messenger msg-messenger">
          <aside class="chat-list panel">
            <div class="chat-search f-search">
              <span class="f-search-icon" aria-hidden="true">⌕</span>
              <input v-model="inboxFilters.search" placeholder="Search names, usernames, messages…" @input="onSearchInput" @keyup.enter="applyInboxFilters" />
              <button v-if="inboxFilters.search" class="f-clear" title="Clear search" @click="clearSearch">×</button>
            </div>
            <div class="chat-filters f-grid">
              <label class="f-field"><span>Platform</span>
                <select v-model="inboxFilters.platform" @change="inboxFilters.account = ''; applyInboxFilters()">
                  <option value="">All</option>
                  <option value="instagram">Instagram</option>
                  <option value="telegram">Telegram</option>
                  <option value="bale">Bale</option>
                </select>
              </label>
              <label class="f-field"><span>Account</span>
                <select v-model="inboxFilters.account" :disabled="!inboxAccountOptions.length" @change="applyInboxFilters">
                  <option value="">All</option>
                  <option v-for="acc in inboxAccountOptions" :key="acc.id" :value="acc.username || acc.bot_username || ''" :disabled="!acc.username && !acc.bot_username">
                    {{ acc.name || acc.username || acc.bot_username || acc.id }}<template v-if="acc.username || acc.bot_username"> (@{{ acc.username || acc.bot_username }})</template>
                  </option>
                </select>
              </label>
              <label class="f-field"><span>Status</span>
                <select v-model="inboxFilters.status" @change="applyInboxFilters">
                  <option value="">All</option>
                  <option v-for="status in userStatuses" :key="status" :value="status">{{ status.replaceAll("_", " ") }}</option>
                </select>
              </label>
              <label class="f-field"><span>From</span>
                <input v-model="inboxFilters.date_from" type="date" title="Updated from" @change="applyInboxFilters" />
              </label>
              <label class="f-field"><span>To</span>
                <input v-model="inboxFilters.date_to" type="date" title="Updated to" @change="applyInboxFilters" />
              </label>
              <div class="f-field"><span>{{ activeFilterCount ? `${activeFilterCount} active` : "Filters" }}</span>
                <button class="quiet f-reset" :disabled="!activeFilterCount" @click="resetInboxFilters">Reset</button>
              </div>
            </div>
            <div class="chat-items">
              <button v-for="item in conversations?.items" :key="`${item.platform}-${item.account_username || ''}-${item.user_id}`" class="chat-item" :class="{ active: selectedConversation?.user_id === item.user_id && selectedConversation?.platform === item.platform && (selectedConversation?.account_username || '') === (item.account_username || '') }" @click="chooseConversation(item)">
                <span class="avatar">{{ (item.first_name || item.username || item.user_id || "?").slice(0, 1).toUpperCase() }}</span>
                <span class="chat-item-body">
                  <span class="chat-item-top">
                    <strong>{{ item.first_name || item.username || item.user_id }}</strong>
                    <time :title="formatTime(item.updated_at)">{{ formatRelativeTime(item.updated_at) }}</time>
                  </span>
                  <span class="chat-item-tags">
                    <img v-if="platformIcon(item.platform)" class="platform-icon" :src="platformIcon(item.platform)" :alt="item.platform" :title="platformMeta[item.platform as keyof typeof platformMeta]?.name || item.platform" />
                    <span class="chat-item-account">{{ item.account_username ? `@${item.account_username}` : '' }}</span>
                    <span class="tag status-tag" :class="statusTagClass(item.status)">{{ (item.status || '').replaceAll("_", " ") }}</span>
                  </span>
                  <span class="chat-preview">{{ item.direct_messages?.[0]?.text || "No messages" }}</span>
                </span>
              </button>
              <p v-if="inboxLoading" class="empty">Loading conversations…</p>
              <p v-else-if="!conversations?.items.length" class="empty">No conversations match these filters.</p>
            </div>
            <div v-if="conversations && conversations.items.length < conversations.total" class="chat-more">
              <button class="quiet" :disabled="inboxLoadingMore" @click="loadMoreConversations">{{ inboxLoadingMore ? "Loading…" : `Show more (${conversations.items.length} / ${conversations.total})` }}</button>
            </div>
          </aside>
          <div class="panel chat">
            <template v-if="selectedConversation">
              <div class="chat-header">
                <span class="avatar">{{ (selectedConversation.first_name || selectedConversation.username || "?").slice(0, 1).toUpperCase() }}</span>
                <div class="chat-header-main">
                  <strong>{{ selectedConversation.first_name || selectedConversation.username || selectedConversation.user_id }}</strong>
                  <small class="muted">@{{ selectedConversation.username || selectedConversation.user_id }}<template v-if="selectedConversation.account_username"> · via @{{ selectedConversation.account_username }}</template></small>
                </div>
                <div class="chat-header-right">
                  <span class="tag status-tag" :class="statusTagClass(selectedConversation.status)">{{ (selectedConversation.status || "").replaceAll("_", " ") }}</span>
                  <img v-if="platformIcon(selectedConversation.platform)" class="platform-icon chat-header-platform-icon" :src="platformIcon(selectedConversation.platform)" :alt="selectedConversation.platform" :title="platformMeta[selectedConversation.platform as keyof typeof platformMeta]?.name || selectedConversation.platform" />
                </div>
              </div>
              <div class="messages" data-thread-scroll>
                <p v-if="threadLoading" class="empty">Loading thread…</p>
                <template v-else>
                  <div v-for="(item, index) in conversationMessages" :key="index" class="bubble-row" :class="item.role === 'user' ? 'incoming' : 'outgoing'">
                    <span class="bubble-icon" :title="roleMeta[item.role]?.label || item.role">{{ roleMeta[item.role]?.icon || "💬" }}</span>
                    <div class="bubble" :class="item.role">
                      <span class="bubble-role">{{ roleMeta[item.role]?.label || item.role }} · {{ formatTime(item.timestamp) }}</span>
                      {{ item.text }}
                    </div>
                  </div>
                  <p v-if="!conversationMessages.length" class="empty">No messages in this thread yet.</p>
                </template>
              </div>
              <form class="composer" @submit.prevent="sendReply">
                <textarea v-model="reply" rows="2" maxlength="4000" placeholder="Write a reply… (Enter to send)" @keydown.enter.exact.prevent="sendReply" />
                <div class="composer-side">
                  <small class="muted">{{ reply.length }}/4000</small>
                  <button :disabled="replySending || !reply.trim()">{{ replySending ? "Sending…" : "Send" }}</button>
                </div>
              </form>
            </template>
            <div v-else class="empty chat-placeholder">
              <p style="font-size: 2rem; margin: 0 0 .5rem;">💬</p>
              <p><strong>Select a conversation</strong> to view the full thread and reply.</p>
              <p class="muted">Tip: filters here are shared with the Broadcast audience.</p>
              <button class="quiet" @click="msgTab = 'broadcast'">Go to Broadcast →</button>
            </div>
          </div>
        </div>

        <!-- ── Broadcast (POST /broadcasts/custom + POST /broadcasts/telegram) ── -->
        <div v-else class="bc-grid">
          <form class="panel form bc-compose" @submit.prevent="broadcast">
            <div class="bc-mode" role="radiogroup" aria-label="Broadcast mode">
              <button type="button" class="bc-mode-card" :class="{ active: broadcastMode === 'targeted' }" @click="broadcastMode = 'targeted'; previewAudience()">
                <strong>🎯 Targeted</strong>
                <small>Filter by platform, account, status… · POST /broadcasts/custom</small>
              </button>
              <button type="button" class="bc-mode-card" :class="{ active: broadcastMode === 'telegram' }" @click="broadcastMode = 'telegram'">
                <strong><img v-if="platformIcon('telegram')" class="tag-icon" :src="platformIcon('telegram')" alt="" />Telegram blast</strong>
                <small>Every Telegram user + optional image · POST /broadcasts/telegram</small>
              </button>
            </div>
            <label>Message <small class="muted">{{ broadcastCharCount }}/4000</small>
              <textarea v-model="broadcastDraft.text" rows="7" maxlength="4000" required placeholder="Write the announcement once — it lands as a Broadcast bubble in every matched thread…" />
            </label>
            <label>Image URL <small class="muted">(HTTPS only{{ broadcastMode === "targeted" ? ", Telegram blast only" : "" }})</small>
              <input v-model="broadcastDraft.image_url" type="url" placeholder="https://… (optional)" />
            </label>
            <p v-if="broadcastDraft.image_url && !broadcastImageValid" class="error">Image URL must start with https://</p>
            <div v-if="broadcastDraft.text.trim()" class="bc-preview">
              <span class="bc-preview-label">Preview</span>
              <div class="bubble-row outgoing"><div class="bubble broadcast"><span class="bubble-role">📢 Broadcast · now</span>{{ broadcastDraft.text.trim() }}</div></div>
            </div>
            <div v-if="broadcastProgress && broadcastProgress.active" class="bc-progress">
              <div class="bc-progress-head">
                <span>Sending… {{ broadcastProgress.current }} / {{ broadcastProgress.total }} ({{ broadcastProgress.percent }}%)</span>
                <span class="muted">{{ broadcastProgress.successful }} delivered · {{ broadcastProgress.failed }} failed</span>
              </div>
              <div class="bc-progress-track"><div class="bc-progress-bar" :style="{ width: broadcastProgress.percent + '%' }"></div></div>
              <div class="bc-progress-bar-label" :class="{ indeterminate: broadcastProgress.total === 0 && broadcastProgress.current === 0 }"></div>
            </div>
            <div v-if="broadcastResult" class="bc-result">
              <div><span>Matched</span><strong>{{ broadcastResult.matched }}</strong></div>
              <div><span>Delivered</span><strong class="ok">{{ broadcastResult.successful }}</strong></div>
              <div><span>Failed</span><strong class="bad">{{ broadcastResult.failed }}</strong></div>
            </div>
            <button :disabled="actionLoading || !broadcastDraft.text.trim() || !broadcastImageValid">{{ actionLoading ? `Sending… ${broadcastProgress ? broadcastProgress.percent + '%' : ''}` : broadcastMode === "telegram" ? "Send Telegram blast" : `Send to ~${audiencePreview.total} conversations` }}</button>
          </form>
          <div class="panel form bc-audience">
            <div class="row"><h2>Audience</h2><button type="button" class="quiet" @click="previewAudience" :disabled="audiencePreview.loading || broadcastMode === 'telegram'">{{ audiencePreview.loading ? "Counting…" : "Refresh count" }}</button></div>
            <p class="muted bc-audience-summary">{{ broadcastAudienceSummary }}<template v-if="broadcastMode === 'targeted'"> · ~{{ audiencePreview.total }} matched</template></p>
            <template v-if="broadcastMode === 'targeted'">
              <div class="f-search">
                <span class="f-search-icon" aria-hidden="true">⌕</span>
                <input v-model="inboxFilters.search" placeholder="Search names, usernames, messages…" @input="onSearchInput" @keyup.enter="applyInboxFilters" />
                <button v-if="inboxFilters.search" type="button" class="f-clear" title="Clear search" @click="clearSearch">×</button>
              </div>
              <div class="f-grid">
                <label class="f-field"><span>Platform</span>
                  <select v-model="inboxFilters.platform" @change="inboxFilters.account = ''; applyInboxFilters()">
                    <option value="">All</option>
                    <option value="instagram">Instagram</option>
                    <option value="telegram">Telegram</option>
                    <option value="bale">Bale</option>
                  </select>
                </label>
                <label class="f-field"><span>Account</span>
                  <select v-model="inboxFilters.account" :disabled="!inboxAccountOptions.length" @change="applyInboxFilters">
                    <option value="">All</option>
                    <option v-for="acc in inboxAccountOptions" :key="acc.id" :value="acc.username || acc.bot_username || ''" :disabled="!acc.username && !acc.bot_username">
                      {{ acc.name || acc.username || acc.bot_username || acc.id }}<template v-if="acc.username || acc.bot_username"> (@{{ acc.username || acc.bot_username }})</template>
                    </option>
                  </select>
                </label>
                <label class="f-field"><span>Status</span>
                  <select v-model="inboxFilters.status" @change="applyInboxFilters">
                    <option value="">All</option>
                    <option v-for="status in userStatuses" :key="status" :value="status">{{ status.replaceAll("_", " ") }}</option>
                  </select>
                </label>
                <label class="f-field"><span>From</span>
                  <input v-model="inboxFilters.date_from" type="date" @change="applyInboxFilters" />
                </label>
                <label class="f-field"><span>To</span>
                  <input v-model="inboxFilters.date_to" type="date" @change="applyInboxFilters" />
                </label>
                <div class="f-field"><span>{{ activeFilterCount ? `${activeFilterCount} active` : "Filters" }}</span>
                  <button type="button" class="quiet f-reset" :disabled="!activeFilterCount" @click="resetInboxFilters">Reset</button>
                </div>
              </div>
              <div class="filter-actions">
                <button type="button" @click="msgTab = 'chats'">View matching chats</button>
              </div>
              <p class="muted">Shared with the Chats filters — what you see is what you send to. The completion notice reports matched, delivered, and failed.</p>
            </template>
            <template v-else>
              <div class="bc-note">
                <p><strong>Blast mode</strong> ignores the filters above and delivers to <strong>all Telegram users</strong> in this workspace.</p>
                <p class="muted">Use Targeted mode when you need Instagram, a single account, or a status slice.</p>
                <button type="button" class="quiet" @click="broadcastMode = 'targeted'; previewAudience()">Switch to Targeted →</button>
              </div>
            </template>
          </div>
        </div>
      </section>
      
      <!-- Redesigned Settings & Multi-Account Management -->
      <section v-else-if="section === 'settings'" class="stack">
        <div class="row">
          <div class="toolbar">
            <button :class="{ quiet: platformFilter !== 'all' }" @click="platformFilter = 'all'">All Accounts ({{ allAccounts.length }})</button>
            <button :class="{ quiet: platformFilter !== 'instagram' }" @click="platformFilter = 'instagram'"><img class="btn-icon" :src="platformMeta.instagram.icon" alt="" />Instagram Pages ({{ workspaceSettings?.platforms.instagram?.accounts?.length || 0 }})</button>
            <button :class="{ quiet: platformFilter !== 'telegram' }" @click="platformFilter = 'telegram'"><img class="btn-icon" :src="platformMeta.telegram.icon" alt="" />Telegram Bots ({{ workspaceSettings?.platforms.telegram?.accounts?.length || 0 }})</button>
            <button :class="{ quiet: platformFilter !== 'bale' }" @click="platformFilter = 'bale'"><img class="btn-icon" :src="platformMeta.bale.icon" alt="" />Bale Bots ({{ workspaceSettings?.platforms.bale?.accounts?.length || 0 }})</button>
          </div>
          <button @click="openAddAccountModal">+ Connect New Account</button>
        </div>

        <div v-if="filteredAccounts.length" class="accounts-grid">
          <article v-for="acc in filteredAccounts" :key="acc.id" class="account-card">
            <div class="account-card-header">
              <div class="account-card-title">
                <div class="account-badges">
                  <span class="badge" :class="acc.platformType"><img class="badge-icon" :src="platformMeta[acc.platformType].icon" alt="" />{{ platformMeta[acc.platformType].name }}</span>
                  <span class="badge" :class="acc.status">{{ acc.status }}</span>
                  <span class="badge" :class="acc.webhook_verified ? 'verified' : 'pending'">{{ acc.webhook_verified ? '✓ Webhook Connected' : '⏳ Setup Pending' }}</span>
                </div>
                <h3>{{ acc.name }}</h3>
                <small v-if="acc.username">@{{ acc.username }}</small>
                <small v-else-if="acc.bot_username">@{{ acc.bot_username }}</small>
                <small v-else-if="acc.ig_id">ID: {{ acc.ig_id }}</small>
                <small v-else>ID: {{ acc.id }}</small>
              </div>
            </div>

            <!-- Webhook URL & Verify Token Box (Instagram only) -->
            <div v-if="acc.platformType === 'instagram'" class="webhook-box">
              <span>Webhook Endpoint URL</span>
              <div class="webhook-box-row">
                <code>{{ acc.webhook_url || 'https://bot.eseminar.cf/instagram' }}</code>
                <button class="quiet" @click="copyToClipboard(acc.webhook_url || 'https://bot.eseminar.cf/instagram')">Copy</button>
              </div>
            </div>

            <div v-if="acc.platformType === 'instagram' && acc.verify_token" class="webhook-box">
              <span>Webhook Verify Token</span>
              <div class="webhook-box-row">
                <code>{{ acc.verify_token }}</code>
                <button class="quiet" @click="copyToClipboard(acc.verify_token)">Copy</button>
              </div>
            </div>

            <!-- Active Modules -->
            <div>
              <small class="muted">Active Automation Modules:</small>
              <div class="module-chips">
                <span v-for="(cfg, modName) in acc.modules" :key="modName" class="module-chip" :class="{ enabled: cfg.enabled }">
                  {{ cfg.enabled ? '✓' : '✗' }} {{ String(modName).replaceAll('_', ' ') }}
                </span>
              </div>
            </div>

            <!-- Card Actions -->
            <div class="card-actions">
              <button class="quiet" :disabled="testingAccountId === acc.id" @click="triggerSetWebhook(acc)">
                {{ testingAccountId === acc.id ? 'Connecting…' : (acc.platformType === 'instagram' ? '🔍 Verify Credentials' : '🔍 Verify Webhook') }}
              </button>
              <button class="quiet" @click="openEditModules(acc)">Configure</button>
              <button class="danger quiet" @click="deleteAccount(acc)">Delete</button>
            </div>
          </article>
        </div>

        <div v-else class="panel empty" style="text-align: center; padding: 3rem 1rem;">
          <h2>No connected accounts yet</h2>
          <p class="muted">Connect your Instagram Pages, Telegram Bots and Bale Bots to enable AI assistance, direct messaging, and automation.</p>
          <button style="margin-top: 1rem;" @click="openAddAccountModal">+ Connect Your First Account</button>
        </div>

        <!-- Workspace Notes -->
        <div class="panel form" style="margin-top: 1.5rem;">
          <h2>Workspace Internal Notes</h2>
          <textarea v-if="workspaceSettings" v-model="workspaceSettings.notes" rows="4" placeholder="Add private operational notes for this workspace…" />
          <button class="quiet" style="align-self: flex-start;" @click="saveWorkspaceNotes">Save Notes</button>
        </div>
      </section>

      <section v-else-if="section === 'system'" class="two-column"><div class="stack"><form class="panel form" @submit.prevent="createClient"><h2>Create workspace</h2><label>Workspace ID<input v-model="clientDraft.username" pattern="[A-Za-z0-9_-]{3,64}" required /></label><label>Business name<input v-model="clientDraft.business_name" required /></label><label>Admin email<input v-model="clientDraft.email" type="email" /></label><label>Initial password<input v-model="clientDraft.password" type="password" minlength="12" required /></label><label>Status<select v-model="clientDraft.status"><option value="inactive">Inactive</option><option value="active">Active</option><option value="trial">Trial</option></select></label><button>Create workspace</button></form><form class="panel form" @submit.prevent="saveCredentials"><h2>Replace integration credentials</h2><label>Workspace ID<input v-model="credentialDraft.username" required /></label><label>Telegram bot token<input v-model="credentialDraft.telegram_access_token" type="password" /></label><label>Bale bot token<input v-model="credentialDraft.bale_access_token" type="password" /></label><label>Instagram page token<input v-model="credentialDraft.page_access_token" type="password" /></label><label>Facebook token<input v-model="credentialDraft.facebook_access_token" type="password" /></label><button>Replace provided credentials</button></form></div><div class="panel table-wrap"><h2>Workspaces</h2><table><thead><tr><th>Workspace</th><th>Business</th><th>Status</th><th>Telegram</th></tr></thead><tbody><tr v-for="client in systemClients" :key="client.username"><td>{{ client.username }}</td><td>{{ client.business_name }}</td><td><span class="badge">{{ client.status }}</span></td><td><button class="quiet" @click="changeSection('system')">Active</button></td></tr></tbody></table><p class="muted">Credentials are write-only and never returned to the browser.</p></div></section>
    </section>

    <!-- Modal: Add New Account -->
    <div v-if="isAddAccountOpen" class="modal-backdrop" @click.self="isAddAccountOpen = false">
      <div class="modal-dialog">
        <div class="modal-header">
          <h2>Connect New Account</h2>
          <button class="modal-close" @click="isAddAccountOpen = false">×</button>
        </div>

        <form class="form" @submit.prevent="createAccount">
          <!-- Step 1: Platform Selection -->
          <label>Select Platform</label>
          <div class="platform-selector">
            <div class="platform-option" :class="{ selected: accountDraft.platform === 'telegram' }" @click="accountDraft.platform = 'telegram'">
              <img class="platform-option-icon" :src="platformMeta.telegram.icon" alt="Telegram" />
              Telegram Bot
            </div>
            <div class="platform-option" :class="{ selected: accountDraft.platform === 'bale' }" @click="accountDraft.platform = 'bale'">
              <img class="platform-option-icon" :src="platformMeta.bale.icon" alt="Bale" />
              Bale Bot
            </div>
            <div class="platform-option" :class="{ selected: accountDraft.platform === 'instagram' }" @click="accountDraft.platform = 'instagram'">
              <img class="platform-option-icon" :src="platformMeta.instagram.icon" alt="Instagram" />
              Instagram Page
            </div>
          </div>

          <label>Account Label / Name
            <input v-model="accountDraft.name" placeholder="e.g. Support Bot or Official Page" required />
          </label>

          <label v-if="accountDraft.platform === 'instagram'">Instagram Username / Page Handle
            <input v-model="accountDraft.username" placeholder="e.g. cozmoz_trade_shop" required />
          </label>

          <!-- Telegram Specific Inputs -->
          <template v-if="accountDraft.platform === 'telegram'">
            <label>Telegram Bot Token
              <input v-model="accountDraft.telegram_access_token" type="password" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" required />
              <small class="muted">Obtain this token from @BotFather on Telegram. The bot will be connected automatically — no webhook setup needed.</small>
            </label>
          </template>

          <!-- Bale Specific Inputs -->
          <template v-else-if="accountDraft.platform === 'bale'">
            <label>Bale Bot Token
              <input v-model="accountDraft.bale_access_token" type="password" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" required />
              <small class="muted">Obtain this token from @botfather on Bale (https://ble.ir/botfather). The bot will be connected automatically — uses tapi.bale.ai.</small>
            </label>
          </template>

          <!-- Instagram Specific Inputs -->
          <template v-else>
            <label>Instagram Account ID (Numeric)
              <input v-model="accountDraft.ig_id" placeholder="e.g. 17841450057515962" required />
            </label>

            <label>Instagram Page Access Token
              <input v-model="accountDraft.page_access_token" type="password" placeholder="IGAAJZ..." required />
            </label>

            <label>Facebook Graph Access Token <small class="muted">(Optional)</small>
              <input v-model="accountDraft.facebook_access_token" type="password" placeholder="EAAOw..." />
            </label>

            <div class="webhook-box">
              <span>Verify Token (auto-generated)</span>
              <div class="webhook-box-row">
                <code>{{ accountDraft.verify_token }}</code>
                <button type="button" class="quiet" @click="accountDraft.verify_token = generateSecretPhrase()">Regenerate</button>
              </div>
              <small class="muted">Enter this exact verify token in Meta App Dashboard Webhook settings.</small>
            </div>

            <div class="webhook-box">
              <span>Meta Webhook Callback URL</span>
              <code>https://bot.eseminar.cf/instagram</code>
            </div>

            <label class="toggle">
              <input v-model="accountDraft.set_webhook_now" type="checkbox" />
              Verify credentials with Graph API upon saving
            </label>
          </template>

          <!-- Modules Toggles -->
          <label>Enable Automation Modules</label>
          <div v-if="!hasAgents" class="muted" style="color:#b77900; display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; margin-bottom:0.5rem;"><span>⚠️</span> DM & Orderbook unavailable — create an agent first.</div>
          <div v-if="!hasVisionModel" class="muted" style="color:#b77900; display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; margin-bottom:0.5rem;"><span>⚠️</span> Vision AI unavailable — no vision model found.</div>
          <div class="module-toggle-grid">
            <label class="toggle"><input v-model="accountDraft.modules.fixed_response.enabled" type="checkbox" /> Fixed Replies</label>
            <label class="toggle" :class="{ muted: !hasAgents }" :title="!hasAgents ? moduleDisabledReason('dm_assist') : ''"><input v-model="accountDraft.modules.dm_assist.enabled" type="checkbox" :disabled="!hasAgents" @change="if(!hasAgents && accountDraft.modules.dm_assist.enabled){ accountDraft.modules.dm_assist.enabled=false; fail(moduleDisabledReason('dm_assist')) }" /> DM AI Assistant</label>
            <label v-if="accountDraft.platform === 'instagram'" class="toggle"><input v-model="accountDraft.modules.comment_assist.enabled" type="checkbox" /> Comment Assist</label>
            <label class="toggle" :class="{ muted: !hasVisionModel }" :title="!hasVisionModel ? moduleDisabledReason('vision') : ''"><input v-model="accountDraft.modules.vision.enabled" type="checkbox" :disabled="!hasVisionModel" @change="if(!hasVisionModel && accountDraft.modules.vision.enabled){ accountDraft.modules.vision.enabled=false; fail(moduleDisabledReason('vision')) }" /> Vision AI</label>
            <label class="toggle" :class="{ muted: !hasAgents }" :title="!hasAgents ? moduleDisabledReason('orderbook') : ''"><input v-model="accountDraft.modules.orderbook.enabled" type="checkbox" :disabled="!hasAgents" @change="if(!hasAgents && accountDraft.modules.orderbook.enabled){ accountDraft.modules.orderbook.enabled=false; fail(moduleDisabledReason('orderbook')) }" /> Orderbook</label>
          </div>

          <div style="display: flex; gap: .75rem; justify-content: flex-end; margin-top: .5rem;">
            <button type="button" class="quiet" @click="isAddAccountOpen = false">Cancel</button>
            <button :disabled="actionLoading">{{ actionLoading ? 'Connecting…' : 'Save & Connect' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal: Configure Account Modules -->
    <div v-if="isEditModulesOpen && selectedAccountForEdit" class="modal-backdrop" @click.self="isEditModulesOpen = false">
      <div class="modal-dialog">
        <div class="modal-header">
          <h2>Configure {{ selectedAccountForEdit.name }}</h2>
          <button class="modal-close" @click="isEditModulesOpen = false">×</button>
        </div>

        <form class="form" @submit.prevent="saveAccountModules">
          <label>Account Label
            <input v-model="selectedAccountForEdit.name" required />
          </label>

          <template v-if="isInstagramAccount(selectedAccountForEdit)">
            <label>Account Username / Handle
              <input v-model="selectedAccountForEdit.username" placeholder="e.g. handle or bot_username" />
            </label>
          </template>
          <template v-else>
            <div class="muted" style="font-size:0.85rem; margin-bottom:0.6rem;">Bot username is set automatically via webhook: <strong>@{{ selectedAccountForEdit.bot_username || selectedAccountForEdit.username || 'pending' }}</strong></div>
          </template>

          <label>Status
            <select v-model="selectedAccountForEdit.status">
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>

          <label>Automation Modules</label>
          <div v-if="!hasAgents" class="muted" style="color:#b77900; display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; margin-bottom:0.5rem;"><span>⚠️</span> DM & Orderbook unavailable — create an agent first.</div>
          <div v-if="!hasVisionModel" class="muted" style="color:#b77900; display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; margin-bottom:0.5rem;"><span>⚠️</span> Vision AI unavailable — no vision model found.</div>
          <div class="module-toggle-grid">
            <label class="toggle"><input v-model="selectedAccountForEdit.modules.fixed_response.enabled" type="checkbox" /> Fixed Replies</label>
            <label class="toggle" :class="{ muted: !hasAgents }" :title="!hasAgents ? moduleDisabledReason('dm_assist') : ''"><input v-model="selectedAccountForEdit.modules.dm_assist.enabled" type="checkbox" :disabled="!hasAgents" @change="if(!hasAgents && selectedAccountForEdit.modules.dm_assist.enabled){ selectedAccountForEdit.modules.dm_assist.enabled=false; fail(moduleDisabledReason('dm_assist')) }" /> DM AI Assistant</label>
            <label class="toggle"><input v-model="selectedAccountForEdit.modules.comment_assist.enabled" type="checkbox" /> Comment Assist</label>
            <label class="toggle" :class="{ muted: !hasVisionModel }" :title="!hasVisionModel ? moduleDisabledReason('vision') : ''"><input v-model="selectedAccountForEdit.modules.vision.enabled" type="checkbox" :disabled="!hasVisionModel" @change="if(!hasVisionModel && selectedAccountForEdit.modules.vision.enabled){ selectedAccountForEdit.modules.vision.enabled=false; fail(moduleDisabledReason('vision')) }" /> Vision AI</label>
            <label class="toggle" :class="{ muted: !hasAgents }" :title="!hasAgents ? moduleDisabledReason('orderbook') : ''"><input v-model="selectedAccountForEdit.modules.orderbook.enabled" type="checkbox" :disabled="!hasAgents" @change="if(!hasAgents && selectedAccountForEdit.modules.orderbook.enabled){ selectedAccountForEdit.modules.orderbook.enabled=false; fail(moduleDisabledReason('orderbook')) }" /> Orderbook</label>
          </div>

          <div style="display: flex; gap: .75rem; justify-content: flex-end; margin-top: .5rem;">
            <button type="button" class="quiet" @click="isEditModulesOpen = false">Cancel</button>
            <button :disabled="actionLoading">{{ actionLoading ? 'Saving…' : 'Save Changes' }}</button>
          </div>
        </form>
      </div>
    </div>
  </main>
</template>

