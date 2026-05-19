import { useEffect, useState } from "react";
import { tg } from "../lib/telegram";

interface Props {
  tally: { correct: number; wrong: number };
  sessionType: string;
  totalDue: number;
  onReviewMore: () => void;
}

const SESSION_LABEL: Record<string, string> = {
  morning: "🌅 Morning",
  lunch: "🌞 Lunch",
  dinner: "🌙 Dinner",
  on_demand: "📚 On-demand",
};

export function SummaryScreen({ tally, sessionType, totalDue, onReviewMore }: Props) {
  const total = tally.correct + tally.wrong;
  const accuracy = total > 0 ? Math.round((tally.correct / total) * 100) : 0;
  const [closing, setClosing] = useState(false);
  const hasMore = totalDue > total;

  // Promote the Telegram main button as the primary close action.
  useEffect(() => {
    const w = tg();
    if (!w?.MainButton) return;
    w.MainButton.setText("Close");
    w.MainButton.show();
    const cb = () => {
      setClosing(true);
      w.close();
    };
    w.MainButton.onClick(cb);
    return () => w.MainButton?.hide();
  }, []);

  return (
    <div className="screen center">
      <header>
        <div className="badge">{SESSION_LABEL[sessionType] ?? "📚"}</div>
        <h1>Session done</h1>
      </header>

      {total === 0 ? (
        <p className="muted">No flashcards in this session.</p>
      ) : (
        <>
          <div className="stat-row">
            <div className="stat">
              <div className="stat-num good">{tally.correct}</div>
              <div className="stat-label">Correct</div>
            </div>
            <div className="stat">
              <div className="stat-num bad">{tally.wrong}</div>
              <div className="stat-label">Missed</div>
            </div>
            <div className="stat">
              <div className="stat-num">{accuracy}%</div>
              <div className="stat-label">Accuracy</div>
            </div>
          </div>
        </>
      )}

      <p className="muted small">
        {totalDue > total
          ? `${totalDue - total} more items still due today.`
          : "All caught up for today!"}
      </p>

      <div className="actions">
        {hasMore && (
          <button className="btn btn-got" onClick={onReviewMore}>
            🔁 Review more
          </button>
        )}
        {!tg()?.MainButton && (
          <button className="btn ghost" onClick={() => tg()?.close()}>
            Close
          </button>
        )}
      </div>

      {closing && <p className="muted small">Closing…</p>}
    </div>
  );
}
