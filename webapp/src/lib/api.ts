import { tg } from "./telegram";

const API_BASE = (import.meta.env.VITE_API_BASE as string) ?? "";

export interface Card {
  item_progress_id: string;
  arabic: string;
  transliteration: string;
  translation: string;
  type: string;
  root: string;
  plural: string;
  example_sentence: string;
  example_translation: string;
  test_type: "meaning" | "plural" | "fill_blank" | "root_derive" | "grammar";
  srs_level: number;
  streak: number;
  lapse_count: number;
}

export interface Passage {
  id: string;
  title: string;
  text_arabic: string;
  text_english: string;
  words_used: string[];
  comprehension_questions: string[];
  difficulty: string;
}

export interface Session {
  session_id: string;
  session_type: string;
  total_due_today: number;
  cards: Card[];
  passage: Passage | null;
}

export interface LookupResult {
  found: boolean;
  arabic: string;
  transliteration?: string;
  translation?: string;
  type?: string;
  root?: string;
  plural?: string;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const initData = tg()?.initData ?? "";
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok && res.status !== 404) {
    const body = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${body}`);
  }
  return (await res.json()) as T;
}

export function fetchSession(sessionType: string): Promise<Session> {
  return request<Session>(
    `/api/session?session_type=${encodeURIComponent(sessionType)}`,
  );
}

export function submitResult(args: {
  item_progress_id: string;
  correct: boolean;
  test_type: string;
  session_type: string;
}) {
  return request<{ ok: true; srs_level: number; next_review_at: string }>(
    "/api/session/result",
    { method: "POST", body: JSON.stringify(args) },
  );
}

export function lookupWord(arabic: string): Promise<LookupResult> {
  return request<LookupResult>(`/api/lookup?arabic=${encodeURIComponent(arabic)}`);
}

export function addRawWord(text: string) {
  return request<{ ok: true }>("/api/raw_words", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function markPassageShown(passage_id: string) {
  return request<{ ok: true }>("/api/passage/shown", {
    method: "POST",
    body: JSON.stringify({ passage_id }),
  });
}
