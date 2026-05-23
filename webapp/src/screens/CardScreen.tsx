import { MouseEvent, useEffect, useState } from "react";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { Card } from "../lib/api";
import { haptic } from "../lib/telegram";

interface SubmitResponse {
  correct: boolean;
  correct_answer: string;
}

interface Props {
  card: Card;
  index: number;
  total: number;
  submit: (args: {
    correct: boolean;
    chosen?: string;
    format: "reveal" | "mcq";
  }) => Promise<SubmitResponse>;
  onRated: (correct: boolean) => void;
}

const TEST_TYPE_LABELS: Record<string, string> = {
  meaning: "💬 What does this mean?",
  plural: "📚 What is the plural (جمع)?",
  fill_blank: "✏️ Fill in the blank",
  root_derive: "🌱 Derive from the root",
  grammar: "📐 Apply the grammar rule",
};

export function CardScreen({ card, index, total, submit, onRated }: Props) {
  if (card.format === "mcq" && card.options.length > 0) {
    return (
      <McqCardScreen
        card={card}
        index={index}
        total={total}
        submit={submit}
        onRated={onRated}
      />
    );
  }
  return (
    <RevealCardScreen
      card={card}
      index={index}
      total={total}
      submit={submit}
      onRated={onRated}
    />
  );
}

function CardHeader({ index, total }: { index: number; total: number }) {
  return (
    <header className="progress">
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${((index + 1) / total) * 100}%` }}
        />
      </div>
      <div className="progress-text">
        {index + 1} / {total}
      </div>
    </header>
  );
}

function CardStatus({ card }: { card: Card }) {
  return (
    <div className="card-status">
      SRS {card.srs_level}/8 · {"⭐".repeat(Math.min(card.srs_level, 8))}
      {card.streak >= 2 && <> · 🔥 {card.streak}</>}
      {card.lapse_count >= 4 && <> · 🩸 leech</>}
    </div>
  );
}

function RevealCardScreen({ card, index, total, submit, onRated }: Props) {
  const [revealed, setRevealed] = useState(false);
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 0, 200], [-15, 0, 15]);
  const opacity = useTransform(x, [-200, -50, 0, 50, 200], [0.4, 1, 1, 1, 0.4]);

  function next(correct: boolean) {
    submit({ correct, format: "reveal" }).catch((e) =>
      console.error("submitResult failed", e),
    );
    setRevealed(false);
    x.set(0);
    onRated(correct);
  }

  function onDragEnd(_e: unknown, info: { offset: { x: number } }) {
    if (!revealed) {
      x.set(0);
      return;
    }
    if (info.offset.x > 100) next(true);
    else if (info.offset.x < -100) next(false);
    else x.set(0);
  }

  function onCardTap(event: MouseEvent<HTMLDivElement>) {
    if (!revealed) {
      haptic("light");
      setRevealed(true);
      return;
    }
    haptic("medium");
    const rect = event.currentTarget.getBoundingClientRect();
    const tappedRight = event.clientX - rect.left > rect.width / 2;
    const target = tappedRight ? 300 : -300;
    animate(x, target, { duration: 0.25, ease: "easeOut" }).then(() =>
      next(tappedRight),
    );
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === " " || e.key === "Enter") {
        if (!revealed) {
          e.preventDefault();
          setRevealed(true);
        }
        return;
      }
      if (!revealed) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        next(true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        next(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [revealed]);

  return (
    <div className="screen" key={card.item_progress_id}>
      <CardHeader index={index} total={total} />

      <motion.div
        className="card"
        drag={revealed ? "x" : false}
        dragConstraints={{ left: 0, right: 0 }}
        style={{ x, rotate, opacity }}
        onDragEnd={onDragEnd}
        onClick={onCardTap}
        whileTap={{ scale: 0.99 }}
      >
        <div className="card-label">{TEST_TYPE_LABELS[card.test_type] ?? "💬 Review"}</div>

        <CardFront card={card} />

        {revealed && <CardBack card={card} />}

        <CardStatus card={card} />

        {!revealed ? (
          <div className="hint">Tap or press space to reveal</div>
        ) : (
          <div className="hint">Tap right for ✅ · tap left for ❌</div>
        )}
      </motion.div>

      <div className="actions">
        <button
          className="btn btn-miss"
          disabled={!revealed}
          onClick={() => next(false)}
        >
          ❌ Missed
        </button>
        <button
          className="btn btn-got"
          disabled={!revealed}
          onClick={() => next(true)}
        >
          ✅ Got it
        </button>
      </div>
    </div>
  );
}

function McqCardScreen({ card, index, total, submit, onRated }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<SubmitResponse | null>(null);
  const [pending, setPending] = useState(false);

  function pick(option: string) {
    if (chosen) return;
    setChosen(option);
    setPending(true);
    submit({ correct: false, chosen: option, format: "mcq" })
      .then((r) => setVerdict(r))
      .catch((e) => {
        console.error("submitResult failed", e);
        // Best-effort fallback: treat as wrong and let the user move on.
        setVerdict({ correct: false, correct_answer: "" });
      })
      .finally(() => setPending(false));
  }

  function advance() {
    if (!verdict) return;
    onRated(verdict.correct);
  }

  function optionClass(opt: string): string {
    if (!verdict) return "btn mcq-option";
    if (opt === verdict.correct_answer) return "btn mcq-option mcq-correct";
    if (opt === chosen) return "btn mcq-option mcq-wrong";
    return "btn mcq-option mcq-dim";
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!verdict) return;
      if (e.key === " " || e.key === "Enter" || e.key === "ArrowRight") {
        e.preventDefault();
        advance();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [verdict]);

  return (
    <div className="screen" key={card.item_progress_id}>
      <CardHeader index={index} total={total} />

      <div className="card">
        <div className="card-label">{TEST_TYPE_LABELS[card.test_type] ?? "💬 Review"}</div>
        <CardFront card={card} />
        <CardStatus card={card} />
        <div className="hint">
          {!chosen
            ? "Pick the correct answer"
            : pending
              ? "Checking…"
              : verdict?.correct
                ? "✅ Correct"
                : "❌ Not quite"}
        </div>
      </div>

      <div className="mcq-options">
        {card.options.map((opt) => (
          <button
            key={opt}
            className={optionClass(opt)}
            onClick={() => pick(opt)}
            disabled={!!chosen}
          >
            {opt}
          </button>
        ))}
      </div>

      <div className="actions">
        <button
          className="btn btn-got"
          disabled={!verdict}
          onClick={advance}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

function CardFront({ card }: { card: Card }) {
  switch (card.test_type) {
    case "meaning":
      return (
        <div className="card-front">
          <div className="arabic-big">{card.arabic}</div>
          {card.transliteration && (
            <div className="trans">({card.transliteration})</div>
          )}
        </div>
      );
    case "plural":
      return (
        <div className="card-front">
          <div className="arabic-big">{card.arabic}</div>
          <div className="trans">— {card.translation}</div>
          <div className="prompt">What is the plural (جمع)?</div>
        </div>
      );
    case "root_derive":
      return (
        <div className="card-front">
          <div className="prompt">Root</div>
          <div className="arabic-big">{card.root}</div>
          <div className="prompt">
            Derive the word that means: <strong>{card.translation}</strong>
          </div>
        </div>
      );
    case "fill_blank": {
      const sentence = card.example_sentence
        ? blankWordInSentence(card.example_sentence, card.arabic)
        : card.arabic;
      return (
        <div className="card-front">
          <div className="arabic-medium">{sentence}</div>
        </div>
      );
    }
    case "grammar":
      return (
        <div className="card-front">
          <div className="prompt">📐 Grammar rule</div>
          <div className="arabic-big">{card.arabic}</div>
          <div className="trans">{card.translation}</div>
        </div>
      );
  }
}

function CardBack({ card }: { card: Card }) {
  switch (card.test_type) {
    case "meaning":
      return (
        <div className="card-back">
          <div className="reveal">➡ {card.translation}</div>
        </div>
      );
    case "plural":
      return (
        <div className="card-back">
          <div className="arabic-medium">{card.plural || "—"}</div>
        </div>
      );
    case "root_derive":
      return (
        <div className="card-back">
          <div className="arabic-medium">{card.arabic}</div>
          {card.transliteration && (
            <div className="trans">({card.transliteration})</div>
          )}
        </div>
      );
    case "fill_blank":
      return (
        <div className="card-back">
          <div className="arabic-medium">{card.arabic}</div>
          <div className="reveal">{card.translation}</div>
          {card.example_translation && (
            <div className="muted small">📝 {card.example_translation}</div>
          )}
        </div>
      );
    case "grammar":
      return (
        <div className="card-back">
          {card.example_sentence && (
            <div className="arabic-medium">{card.example_sentence}</div>
          )}
        </div>
      );
  }
}

// Replace the target word in `sentence` with a blank, tolerating Arabic
// diacritic differences and an optional definite-article (الـ) prefix on the
// sentence token. Falls back to exact replace, then to the original sentence.
const ARABIC_DIACRITICS = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]/g;

function stripDiacritics(s: string): string {
  return s.replace(ARABIC_DIACRITICS, "");
}

function blankWordInSentence(sentence: string, word: string): string {
  const target = stripDiacritics(word).replace(/^\u0627\u0644/, "");
  if (!target) return sentence;

  const tokens = sentence.split(/(\s+)/);
  let replaced = false;
  const out = tokens.map((tok) => {
    if (replaced || /^\s*$/.test(tok) || !tok) return tok;
    const match = tok.match(/^([\u0600-\u06FF\u0750-\u077F]+)(.*)$/);
    if (!match) return tok;
    const [, core, rest] = match;
    const normalized = stripDiacritics(core).replace(/^\u0627\u0644/, "");
    if (normalized === target) {
      replaced = true;
      return "________" + rest;
    }
    return tok;
  });
  return replaced ? out.join("") : sentence;
}
