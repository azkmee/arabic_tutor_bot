import { useState } from "react";
import { motion, useMotionValue, useTransform } from "framer-motion";
import { Card } from "../lib/api";

interface Props {
  card: Card;
  index: number;
  total: number;
  onRated: (correct: boolean) => void;
}

const TEST_TYPE_LABELS: Record<string, string> = {
  meaning: "💬 What does this mean?",
  plural: "📚 What is the plural (جمع)?",
  fill_blank: "✏️ Fill in the blank",
  root_derive: "🌱 Derive from the root",
  grammar: "📐 Apply the grammar rule",
};

export function CardScreen({ card, index, total, onRated }: Props) {
  const [revealed, setRevealed] = useState(false);
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 0, 200], [-15, 0, 15]);
  const opacity = useTransform(x, [-200, -50, 0, 50, 200], [0.4, 1, 1, 1, 0.4]);

  // Reset when card changes
  function next(correct: boolean) {
    setRevealed(false);
    x.set(0);
    onRated(correct);
  }

  function onDragEnd(_e: unknown, info: { offset: { x: number } }) {
    if (!revealed) {
      // Snap back if user hasn't flipped yet — don't accidentally rate.
      x.set(0);
      return;
    }
    if (info.offset.x > 100) next(true);
    else if (info.offset.x < -100) next(false);
    else x.set(0);
  }

  return (
    <div className="screen" key={card.item_progress_id}>
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

      <motion.div
        className="card"
        drag={revealed ? "x" : false}
        dragConstraints={{ left: 0, right: 0 }}
        style={{ x, rotate, opacity }}
        onDragEnd={onDragEnd}
        onClick={() => setRevealed(true)}
        whileTap={{ scale: 0.99 }}
      >
        <div className="card-label">{TEST_TYPE_LABELS[card.test_type] ?? "💬 Review"}</div>

        <CardFront card={card} />

        {revealed && <CardBack card={card} />}

        <div className="card-status">
          SRS {card.srs_level}/8 · {"⭐".repeat(Math.min(card.srs_level, 8))}
          {card.streak >= 2 && <> · 🔥 {card.streak}</>}
          {card.lapse_count >= 4 && <> · 🩸 leech</>}
        </div>

        {!revealed ? (
          <div className="hint">Tap to reveal</div>
        ) : (
          <div className="hint">Swipe ← missed · got it →</div>
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
        ? card.example_sentence.replace(card.arabic, "________")
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
