import { useState } from "react";
import { api } from "../../api/client";
import type { BriefingResponse, Notification } from "../../api/types";
import { Icon, Panel, ProviderNote, SimTag } from "../../components/ui";

/** SMS links use FAULTZY_PUBLIC_BASE_URL; open the path on this origin. */
const localPath = (url: string) => {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
};

export function TechnicianPanel({ incidentId, notifications }: { incidentId: string; notifications: Notification[] }) {
  const latest = notifications[notifications.length - 1];
  return (
    <Panel
      title="Technician"
      id="technician"
      actions={
        latest && (
          <a className="btn sm" href={localPath(latest.inspection_url)} target="_blank" rel="noreferrer">
            Technician view <Icon name="external" />
          </a>
        )
      }
    >
      <div className="stack">
        {notifications.length === 0 && <p className="small muted">No text sent yet. Faultzy texts the technician at High priority.</p>}
        {notifications.map((n) => (
          <div key={n.id} className="sms">
            <div className="row xs">
              <Icon name="phone" />
              <span>{n.recipient_label.split(" · ")[0]}</span>
              <span className="mono muted">{n.to_masked}</span>
              <span className="spacer" />
              {n.status === "simulated_sent" && <SimTag title="Recorded, not sent" />}
              {n.status === "sent" && <span className="tag real">Sent</span>}
              {(n.status === "failed" || n.status === "skipped") && <span className="tag fail">Not sent</span>}
            </div>
            <div className="bubble small">{n.body}</div>
            {n.error && <div className="xs warn-text">{n.error}</div>}
          </div>
        ))}
        <Briefing load={() => api.briefing(incidentId)} />
      </div>
    </Panel>
  );
}

export function Briefing({ load }: { load: () => Promise<BriefingResponse> }) {
  const [b, setB] = useState<BriefingResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!b)
    return (
      <div>
        <button
          className="btn sm"
          onClick={() =>
            load()
              .then(setB)
              .catch((e) => setErr(String(e)))
          }
        >
          <Icon name="speaker" /> Spoken briefing
        </button>
        {err && <p className="xs warn-text">{err}</p>}
      </div>
    );
  return (
    <div className="briefing stack">
      {b.audio_url ? <audio controls src={b.audio_url} /> : <span className="xs muted">Voice isn't set up, so here's the text:</span>}
      <p className="small">{b.text}</p>
      <ProviderNote provider={b.provider} status={b.status} />
    </div>
  );
}
