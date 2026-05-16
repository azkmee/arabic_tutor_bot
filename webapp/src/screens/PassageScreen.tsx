import { useState } from "react";
import { Passage, LookupResult, lookupWord, addRawWord, markPassageShown } from "../lib/api";
import { haptic } from "../lib/telegram";

interface Props {
  passage: Passage;
  onDone: () => void;
}

type Lookup =
  | { state: "loading"; word: string }
  | { state: "found"; word: string; result: LookupResult }
  | { state: "missing"; word: string }
  | { state: "added"; word: string }
  | { state: "error"; word: string };

// Arabic word tokenizer: split on whitespace and Arabic punctuation, keep
// the originals so we can render exactly what came in. Strips trailing
// punctuation when looking up so "كتاب." matches "كتاب".
const PUNCT = /[\s.,!?؟،؛:()«»"'،؛؟]+/;

function tokenize(text: string): string[] {
  return text.split(/(\s+)/).filter((t) => t.length > 0);
}

function stripPunct(token: string): string {
  return token.replace(/^[.,!?؟،؛:()«»"']+|[.,!?؟،؛:()«»"']+$/g, "");
}

export function PassageScreen({ passage, onDone }: Props) {
  const [showEnglish, setShowEnglish] = useState(false);
  const [showQuestions, setShowQuestions] = useState(false);
  const [lookup, setLookup] = useState<Lookup | null>(null);

  function onWordTap(rawToken: string) {
    const word = stripPunct(rawToken);
    if (!word || PUNCT.test(word)) return;
    haptic("light");
    setLookup({ state: "loading", word });
    lookupWord(word)
      .then((r) => {
        if (r.found) setLookup({ state: "found", word, result: r });
        else setLookup({ state: "missing", word });
      })
      .catch(() => setLookup({ state: "error", word }));
  }

  function onAddToRecall() {
    if (!lookup || lookup.state !== "missing") return;
    addRawWord(lookup.word)
      .then(() => {
        haptic("medium");
        setLookup({ state: "added", word: lookup.word });
      })
      .catch(() => setLookup({ state: "error", word: lookup.word }));
  }

  function onFinish() {
    markPassageShown(passage.id).catch((e) =>
      console.error("markPassageShown failed", e),
    );
    onDone();
  }

  const tokens = tokenize(passage.text_arabic);

  return (
    <div className="screen">
      <header className="passage-header">
        <span className="badge">📖 Reading</span>
        {passage.title && <h2>{passage.title}</h2>}
      </header>

      <div className="passage" dir="rtl" lang="ar">
        {tokens.map((token, i) =>
          /\s+/.test(token) ? (
            <span key={i}>{token}</span>
          ) : (
            <span
              key={i}
              className="word"
              onClick={() => onWordTap(token)}
            >
              {token}
            </span>
          ),
        )}
      </div>

      <div className="passage-toolbar">
        <button className="btn ghost" onClick={() => setShowEnglish((s) => !s)}>
          {showEnglish ? "Hide" : "Show"} translation
        </button>
        {passage.comprehension_questions.length > 0 && (
          <button className="btn ghost" onClick={() => setShowQuestions((s) => !s)}>
            {showQuestions ? "Hide" : "Show"} questions
          </button>
        )}
      </div>

      {showEnglish && passage.text_english && (
        <div className="passage-english">{passage.text_english}</div>
      )}

      {showQuestions && passage.comprehension_questions.length > 0 && (
        <ol className="questions" dir="rtl" lang="ar">
          {passage.comprehension_questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ol>
      )}

      <div className="actions">
        <button className="btn btn-got" onClick={onFinish}>
          Done
        </button>
      </div>

      {lookup && (
        <div className="modal-backdrop" onClick={() => setLookup(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setLookup(null)}>
              ✕
            </button>
            <div className="arabic-big" dir="rtl" lang="ar">
              {lookup.word}
            </div>
            {lookup.state === "loading" && <p className="muted">Looking up…</p>}
            {lookup.state === "found" && (
              <>
                <p className="trans">{lookup.result.transliteration}</p>
                <p className="reveal">{lookup.result.translation}</p>
                {lookup.result.root && (
                  <p className="muted small">root: {lookup.result.root}</p>
                )}
                {lookup.result.plural && (
                  <p className="muted small">plural: {lookup.result.plural}</p>
                )}
              </>
            )}
            {lookup.state === "missing" && (
              <>
                <p className="muted">Not in your vocabulary yet.</p>
                <button className="btn btn-got" onClick={onAddToRecall}>
                  ➕ Add to recall
                </button>
              </>
            )}
            {lookup.state === "added" && (
              <p className="reveal">✅ Queued for processing</p>
            )}
            {lookup.state === "error" && (
              <p className="muted">Couldn't look that up. Try again.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
