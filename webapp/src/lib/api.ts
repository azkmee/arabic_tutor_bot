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
  format: "reveal" | "mcq";
  options: string[];
  srs_level: number;
  streak: number;
  lapse_count: number;
}

export interface PassageWord {
  arabic: string;
  translation: string;
}

export interface PassageLine {
  arabic: string;
  english: string;
  words: PassageWord[];
}

export interface Passage {
  id: string;
  title: string;
  text_arabic: string;
  text_english: string;
  lines: PassageLine[];
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
  format?: "reveal" | "mcq";
  chosen?: string;
}) {
  return request<{
    ok: true;
    correct: boolean;
    correct_answer: string;
    srs_level: number;
    next_review_at: string;
    streak: number;
  }>("/api/session/result", {
    method: "POST",
    body: JSON.stringify(args),
  });
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

export function fetchNextPassage(excludeId?: string): Promise<{ passage: Passage | null }> {
  const q = excludeId ? `?exclude=${encodeURIComponent(excludeId)}` : "";
  return request<{ passage: Passage | null }>(`/api/passage/next${q}`);
}
