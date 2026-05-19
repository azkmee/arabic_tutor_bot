import { useState } from "react";
import {
  Passage,
  PassageLine,
  PassageWord,
  LookupResult,
  lookupWord,
  addRawWord,
  markPassageShown,
} from "../lib/api";
import { haptic } from "../lib/telegram";

interface Props {
  passage: Passage;
  onDone: () => void;
}

type Lookup =
  | { state: "loading"; word: string }
  | { state: "found"; word: string; result: LookupResult }
  | { state: "gloss"; word: string; translation: string }
  | { state: "missing"; word: string }
  | { state: "added"; word: string }
  | { state: "error"; word: string };

function stripPunct(token: string): string {
  return token.replace(/^[.,!?؟،؛:()«»"']+|[.,!?؟،؛:()«»"']+$/g, "");
}

function tokenize(text: string): string[] {
  return text.split(/(\s+)/).filter((t) => t.length > 0);
}

export function PassageScreen({ passage, onDone }: Props) {
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [showQuestions, setShowQuestions] = useState(false);
  const [showEnglish, setShowEnglish] = useState(false);

  const hasLines = (passage.lines?.length ?? 0) > 0;

  function toggleLine(i: number) {
    haptic("light");
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function showGloss(word: PassageWord) {
    haptic("light");
    if (word.translation) {
      setLookup({
        state: "gloss",
        word: word.arabic,
        translation: word.translation,
      });
    } else {
      remoteLookup(word.arabic);
    }
  }

  function remoteLookup(rawToken: string) {
    const word = stripPunct(rawToken);
    if (!word) return;
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
    if (!lookup) return;
    const word = lookup.word;
    addRawWord(word)
      .then(() => {
        haptic("medium");
        setLookup({ state: "added", word });
      })
      .catch(() => setLookup({ state: "error", word }));
  }

  function onFinish() {
    markPassageShown(passage.id).catch((e) =>
      console.error("markPassageShown failed", e),
    );
    onDone();
  }

  return (
    <div className="screen">
      <header className="passage-header">
        <span className="badge">📖 Reading</span>
        {passage.title && <h2>{passage.title}</h2>}
      </header>

      {hasLines ? (
        <div className="passage-lines">
          {passage.lines.map((line, i) => (
            <LineRow
              key={i}
              line={line}
              expanded={expanded.has(i)}
              onToggle={() => toggleLine(i)}
              onWordTap={showGloss}
            />
          ))}
        </div>
      ) : (
        <FallbackBlob
          text={passage.text_arabic}
          onWordTap={remoteLookup}
        />
      )}

      <div className="passage-toolbar">
        {!hasLines && passage.text_english && (
          <button className="btn ghost" onClick={() => setShowEnglish((s) => !s)}>
            {showEnglish ? "Hide" : "Show"} translation
          </button>
        )}
        {passage.comprehension_questions.length > 0 && (
          <button className="btn ghost" onClick={() => setShowQuestions((s) => !s)}>
            {showQuestions ? "Hide" : "Show"} questions
          </button>
        )}
      </div>

      {!hasLines && showEnglish && passage.text_english && (
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
            {lookup.state === "gloss" && (
              <p className="reveal">{lookup.translation}</p>
            )}
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

function LineRow({
  line,
  expanded,
  onToggle,
  onWordTap,
}: {
  line: PassageLine;
  expanded: boolean;
  onToggle: () => void;
  onWordTap: (word: PassageWord) => void;
}) {
  return (
    <div className="passage-line" onClick={onToggle}>
      <div className="arabic-line" lang="ar">
        {line.words.length > 0 ? (
          line.words.map((w, i) => (
            <span key={i}>
              <span
                className="word"
                onClick={(e) => {
                  e.stopPropagation();
                  onWordTap(w);
                }}
              >
                {w.arabic}
              </span>
              {i < line.words.length - 1 && " "}
            </span>
          ))
        ) : (
          // No per-word gloss available — render the sentence as plain text.
          <span>{line.arabic}</span>
        )}
      </div>
      {expanded && line.english && (
        <div className="english-line">{line.english}</div>
      )}
    </div>
  );
}

function FallbackBlob({
  text,
  onWordTap,
}: {
  text: string;
  onWordTap: (raw: string) => void;
}) {
  const tokens = tokenize(text);
  return (
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
  );
}
