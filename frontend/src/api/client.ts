/**
 * Thin, typed client for the Django REST API (`/api/...`).
 *
 * Authentication: registered users send `Authorization: Token <key>`.
 * Guests send `X-Guest-Token`, issued when they create their first conversation.
 */

const AUTH_KEY = "cd-auth-token";
const GUEST_KEY = "cd-guest-token";

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable (private mode): the session simply isn't remembered */
  }
}

export const session = {
  get authToken() {
    return readStorage(AUTH_KEY);
  },
  set authToken(value: string | null) {
    writeStorage(AUTH_KEY, value);
  },
  get guestToken() {
    return readStorage(GUEST_KEY);
  },
  set guestToken(value: string | null) {
    writeStorage(GUEST_KEY, value);
  },
};

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, string[]>;
  retryAfter?: number;

  constructor(status: number, code: string, message: string, details?: Record<string, string[]>, retryAfter?: number) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
  }

  /** First error message for a given form field, if the API reported one. */
  field(name: string): string | undefined {
    const value = this.details?.[name];
    return Array.isArray(value) ? value[0] : undefined;
  }
}

type Query = Record<string, string | number | undefined>;

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const url = new URL(`/api${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const auth = session.authToken;
  if (auth) headers.Authorization = `Token ${auth}`;
  const guest = session.guestToken;
  if (guest) headers["X-Guest-Token"] = guest;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit",
    });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
  }

  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    if (response.status === 401 && auth) {
      // The saved token is no longer valid (logged out elsewhere or password changed).
      session.authToken = null;
    }
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? "Something went wrong. Please try again.",
      error?.details,
      error?.retry_after_seconds,
    );
  }
  return data as T;
}

/* ------------------------------------------------------------------ types */

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type Role = "administrator" | "student" | "prospective_student" | "guest";

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface AuthResponse {
  success: boolean;
  token: string;
  user: User;
}

export interface Conversation {
  id: number;
  title: string;
  status: "active" | "archived";
  is_guest: boolean;
  message_count?: number;
  created_at: string;
  updated_at: string;
  guest_token?: string;
}

export interface Source {
  type: "faq";
  id: number;
  reference_code: string;
  question: string;
  category: string;
  source_description: string;
  source_url: string | null;
  information_type: "institutional" | "demonstration";
  verification_status: "verified" | "unverified" | "draft";
}

export interface Suggestion {
  faq_id: number;
  question: string;
  category: string;
}

export type ResponseType = "answer" | "clarification" | "fallback" | "small_talk";

export interface Message {
  id: number;
  conversation: number;
  sender_type: "user" | "bot";
  content: string;
  intent: string;
  intent_confidence: number | null;
  similarity_score: number | null;
  response_type: ResponseType | "";
  answered: boolean | null;
  information_type: string;
  is_verified: boolean | null;
  disclaimer: string | null;
  retrieved_faq: number | null;
  sources: Source[];
  suggestions: Suggestion[];
  used_context: boolean;
  timestamp: string;
}

export interface ChatResponse {
  success: true;
  conversation_id: number;
  user_message: { id: number; content: string; timestamp: string };
  bot_response: {
    id: number;
    content: string;
    intent: string;
    intent_confidence: number | null;
    similarity_score: number | null;
    answered: boolean;
    response_type: ResponseType;
    information_type: string | null;
    verification_status: string | null;
    is_verified: boolean | null;
    disclaimer: string | null;
    sources: Source[];
    suggestions: Suggestion[];
    matched_question: string | null;
    used_context: boolean;
    response_time_ms: number;
    timestamp: string;
  };
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  description: string;
  intent: string;
  faq_count: number;
}

export interface FAQ {
  id: number;
  reference_code: string;
  question: string;
  answer: string;
  category: number;
  category_name: string;
  information_type: string;
}

export interface Health {
  success: boolean;
  database: string;
  demo_mode: boolean;
  nlp_model: { status: "ready" | "loading" | "error" | "not_loaded"; loaded: boolean };
}

export interface Overview {
  total_registered_users: number;
  total_conversations: number;
  total_messages: number;
  total_chatbot_questions: number;
  answered_questions: number;
  unanswered_questions: number;
  clarification_requests: number;
  small_talk_messages: number;
  context_assisted_answers: number;
  answer_rate: number;
  average_response_time_ms: number;
  average_answer_similarity: number;
  feedback: { total: number; positive: number; negative: number; neutral: number; average_rating: number };
}

export interface UsagePoint {
  period: string;
  questions: number;
  answered: number;
  unanswered: number;
  conversations: number;
}

export interface Performance {
  total_queries: number;
  average_response_time_ms: number;
  median_response_time_ms: number;
  p95_response_time_ms: number;
  max_response_time_ms: number;
  daily: UsagePoint[];
  monthly: UsagePoint[];
}

export interface PopularQuestions {
  most_frequently_answered_faqs: {
    faq_id: number;
    reference_code: string;
    question: string;
    category: string;
    times_asked: number;
    average_similarity: number;
  }[];
  most_frequent_questions: { question: string; times_asked: number }[];
}

export interface CategoryStatistics {
  categories: {
    category_id: number;
    category: string;
    answered_questions: number;
    average_similarity: number;
    positive_feedback: number;
    negative_feedback: number;
  }[];
}

export interface UnansweredQuestion {
  id: number;
  original_question: string;
  detected_intent: string;
  similarity_score: number | null;
  review_status: "pending" | "resolved" | "dismissed";
  admin_notes: string;
  timestamp: string;
}

export interface DateRange {
  start_date?: string;
  end_date?: string;
}

/* -------------------------------------------------------------- endpoints */

export const api = {
  health: () => request<Health>("GET", "/health/"),

  register: (data: {
    username: string;
    email: string;
    password: string;
    password_confirm: string;
    first_name?: string;
    last_name?: string;
    role: "student" | "prospective_student";
  }) => request<AuthResponse>("POST", "/auth/register/", data),
  login: (username: string, password: string) => request<AuthResponse>("POST", "/auth/login/", { username, password }),
  logout: () => request<void>("POST", "/auth/logout/"),
  profile: () => request<User>("GET", "/auth/profile/"),

  conversations: () => request<Paginated<Conversation>>("GET", "/chat/conversations/", undefined, { page_size: 50 }),
  createConversation: () => request<Conversation>("POST", "/chat/conversations/", {}),
  renameConversation: (id: number, title: string) =>
    request<Conversation>("PATCH", `/chat/conversations/${id}/`, { title }),
  deleteConversation: (id: number) => request<void>("DELETE", `/chat/conversations/${id}/`),
  messages: (id: number) =>
    request<Paginated<Message>>("GET", `/chat/conversations/${id}/messages/`, undefined, { page_size: 100 }),
  ask: (id: number, content: string) => request<ChatResponse>("POST", `/chat/conversations/${id}/messages/`, { content }),
  claimGuestConversations: () => request<{ claimed_conversations: number }>("POST", "/chat/conversations/claim/"),

  sendFeedback: (message: number, rating: number, comment = "") =>
    request<{ id: number }>("POST", "/feedback/", { message, rating, comment }),

  categories: () => request<Paginated<Category>>("GET", "/knowledge/categories/", undefined, { page_size: 50 }),
  faqs: () => request<Paginated<FAQ>>("GET", "/knowledge/faqs/", undefined, { page_size: 100 }),

  overview: (range: DateRange) => request<Overview>("GET", "/analytics/overview/", undefined, { ...range }),
  performance: (range: DateRange) =>
    request<Performance>("GET", "/analytics/response-performance/", undefined, { ...range }),
  popular: (range: DateRange) =>
    request<PopularQuestions>("GET", "/analytics/popular-questions/", undefined, { ...range, limit: 8 }),
  categoryStats: (range: DateRange) =>
    request<CategoryStatistics>("GET", "/analytics/category-statistics/", undefined, { ...range }),
  unanswered: (range: DateRange) =>
    request<Paginated<UnansweredQuestion>>("GET", "/analytics/unanswered-questions/", undefined, {
      ...range,
      review_status: "pending",
      page_size: 25,
    }),
  reviewUnanswered: (id: number, review_status: "resolved" | "dismissed") =>
    request<UnansweredQuestion>("PATCH", `/analytics/unanswered-questions/${id}/`, { review_status }),
};
