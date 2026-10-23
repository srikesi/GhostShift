import { useEffect, useRef, useState } from "react";
import type { IncidentView } from "../../api/types";
import { Panel, ProviderNote } from "../../components/ui";
import { askCopilot, type ChatTurn, type CopilotAnswer } from "./copilotApi";
import "./copilot.css";

const SUGGESTED = [
  "Why was this flagged?",
  "What happens if we wait until the weekend?",
  "Which other parts should we check?",
];

type Entry = { question: string; answer?: CopilotAnswer; error?: string };

/**
 * GhostMode: ask questions about this machine. The model calls GhostShift's specialist agents
 * (diagnostics, prognostics, safety supervisor, maintenance & supply) as read-only tools.
 * It can explain; it cannot approve, order, change priority or send messages.
 */
export function CopilotPanel({ machineId, incident }: { machineId: string; incident: IncidentView | null }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const incidentId = incident?.incident.id ?? null;

  useEffect(() => {
    setEntries([]);
    setDraft("");
  }, [machineId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [entries, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const history: ChatTurn[] = entries.flatMap((e) =>
      e.answer ? [{ role: "user" as const, text: e.question }, { role: "assistant" as const, text: e.answer.answer }] : [],
    );
    setEntries((prev) => [...prev, { question: q }]);
    setDraft("");
    setBusy(true);
    try {
      const answer = await askCopilot({ machine_id: machineId, incident_id: incidentId, question: q, history });
      setEntries((prev) => prev.map((e, i) => (i === prev.length - 1 ? { ...e, answer } : e)));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setEntries((prev) => prev.map((e, i) => (i === prev.length - 1 ? { ...e, error: message } : e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Ask GhostMode" id="copilot">
      <div className="stack copilot">
        {entries.length === 0 && (
          <p className="small muted">
            Ask about {machineId}. GhostMode checks with the diagnostics, prognostics, safety and maintenance agents
            and answers with their numbers. It can explain, but people approve orders and work.
          </p>
        )}
        {entries.map((e, i) => (
          <div key={i} className="copilot-turn">
            <p className="copilot-q small">{e.question}</p>
            {e.answer && <Answer a={e.answer} />}
            {e.error && <div className="notice error small">{e.error}</div>}
          </div>
        ))}
        {busy && <p className="small muted">Checking with the crew…</p>}
        <div ref={endRef} />
        <div className="row wrap copilot-suggest">
          {SUGGESTED.map((s) => (
            <button key={s} type="button" className="btn sm" disabled={busy} onClick={() => ask(s)}>
              {s}
            </button>
          ))}
        </div>
        <form
          className="copilot-form"
          onSubmit={(ev) => {
            ev.preventDefault();
            ask(draft);
          }}
        >
          <textarea
            value={draft}
            rows={2}
            maxLength={2000}
            placeholder="Ask a question…"
            aria-label="Question for GhostMode"
            onChange={(ev) => setDraft(ev.target.value)}
            onKeyDown={(ev) => {
              if (ev.key === "Enter" && !ev.shiftKey) {
                ev.preventDefault();
                ask(draft);
              }
            }}
          />
          <button type="submit" className="btn primary" disabled={busy || !draft.trim()}>
            Ask
          </button>
        </form>
      </div>
    </Panel>
  );
}

function Answer({ a }: { a: CopilotAnswer }) {
  return (
    <div className="copilot-a">
      <div className="row copilot-meta">
        {a.built_in && (
          <span className="tag" title="Answered by GhostShift's built-in rules, not a model">
            Built-in answer
          </span>
        )}
        <ProviderNote provider={a.provider} status={a.status} />
      </div>
      <p className="small copilot-text">{a.answer}</p>
      {a.error && a.status !== "success" && <p className="xs muted">{a.error}</p>}
      {a.tool_calls.length > 0 && (
        <details className="copilot-steps">
          <summary className="xs muted">
            Steps: asked {a.tool_calls.length} {a.tool_calls.length === 1 ? "agent" : "agents"}
          </summary>
          <ol className="clean trace">
            {a.tool_calls.map((t, i) => (
              <li key={i} className={`stage ${t.ok ? "success" : "provider_failure"}`}>
                <span className="dot" aria-hidden />
                <span className="xs">{t.agent}</span>
                <span className="mono xs muted">{t.name}</span>
                <span className="detail xs">{t.summary}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
