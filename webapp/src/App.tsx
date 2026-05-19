import { useEffect, useState } from "react";
import { CardScreen } from "./screens/CardScreen";
import { PassageScreen } from "./screens/PassageScreen";
import { SummaryScreen } from "./screens/SummaryScreen";
import { fetchSession, submitResult, Session } from "./lib/api";
import { haptic, initTelegram } from "./lib/telegram";

type Stage = "loading" | "cards" | "passage" | "summary" | "error";

interface Tally {
  correct: number;
  wrong: number;
}

export function App() {
  const [stage, setStage] = useState<Stage>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [tally, setTally] = useState<Tally>({ correct: 0, wrong: 0 });

  useEffect(() => {
    initTelegram();
    const params = new URLSearchParams(window.location.search);
    const sessionType = params.get("session_type") ?? "on_demand";
    fetchSession(sessionType)
      .then((s) => {
        setSession(s);
        setStage(s.cards.length > 0 ? "cards" : s.passage ? "passage" : "summary");
      })
      .catch((e: Error) => {
        setError(e.message);
        setStage("error");
      });
  }, []);

  async function onSubmitCard(args: {
    correct: boolean;
    chosen?: string;
    format: "reveal" | "mcq";
  }) {
    if (!session) throw new Error("no session");
    const card = session.cards[index];
    return submitResult({
      item_progress_id: card.item_progress_id,
      test_type: card.test_type,
      session_type: session.session_type,
      ...args,
    });
  }

  function onCardRated(correct: boolean) {
    if (!session) return;
    haptic(correct ? "light" : "medium");
    setTally((t) => ({
      correct: t.correct + (correct ? 1 : 0),
      wrong: t.wrong + (correct ? 0 : 1),
    }));
    const next = index + 1;
    if (next >= session.cards.length) {
      setStage(session.passage ? "passage" : "summary");
    } else {
      setIndex(next);
    }
  }

  if (stage === "loading") {
    return <div className="screen center">Loading…</div>;
  }
  if (stage === "error") {
    return (
      <div className="screen center">
        <h2>Couldn't load session</h2>
        <p className="muted">{error}</p>
        <p className="muted small">
          Open this app from a Telegram WebApp button. Direct browser visits
          can't authenticate.
        </p>
      </div>
    );
  }
  if (!session) return null;

  if (stage === "cards") {
    return (
      <CardScreen
        card={session.cards[index]}
        index={index}
        total={session.cards.length}
        submit={onSubmitCard}
        onRated={onCardRated}
      />
    );
  }
  if (stage === "passage" && session.passage) {
    return (
      <PassageScreen
        passage={session.passage}
        onDone={() => setStage("summary")}
      />
    );
  }
  return (
    <SummaryScreen
      tally={tally}
      sessionType={session.session_type}
      totalDue={session.total_due_today}
    />
  );
}
