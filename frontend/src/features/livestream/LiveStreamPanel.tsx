import { useEffect, useState, useRef } from "react";
import { Panel, SeverityPill, SimTag } from "../../components/ui";
import "./livestream.css";

interface LiveStreamPanelProps {
  machineId: string;
}

interface TelemetryPayload {
  index: number;
  timestamp: string;
  values: {
    spindle_motor_current?: number;
    rotational_speed?: number;
    spindle_speed?: number;
    spindle_vib_rms?: number;
    acoustic_db?: number;
    thermal_max_c?: number;
    process_temp?: number;
    air_temp?: number;
    [key: string]: number | undefined;
  };
  anchor_3d?: {
    x: number;
    y: number;
    z: number;
    component: string;
  };
  phase: string;
  severity: "normal" | "watch" | "warning" | "critical";
}

export function LiveStreamPanel({ machineId }: LiveStreamPanelProps) {
  const [telemetry, setTelemetry] = useState<TelemetryPayload | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [smsAlert, setSmsAlert] = useState<string | null>(null);
  const [activeFault, setActiveFault] = useState<"nominal" | "mild" | "critical" | "estop">("nominal");
  const [loading, setLoading] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const sseUrl = `/api/machines/${encodeURIComponent(machineId)}/stream?speed=1.0&loop=true`;
    const es = new EventSource(sseUrl);
    eventSourceRef.current = es;

    es.addEventListener("telemetry", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setTelemetry(data);
      } catch (err) {
        console.error("Failed to parse SSE telemetry:", err);
      }
    });

    es.onerror = () => {
      console.warn("SSE connection interrupted, retrying...");
    };

    return () => {
      es.close();
    };
  }, [machineId]);

  const injectFault = async (type: "mild" | "critical") => {
    setLoading(true);
    try {
      const res = await fetch(`/api/machines/${encodeURIComponent(machineId)}/inject-fault`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fault_type: type }),
      });
      const data = await res.json();
      setActiveFault(type);
      setSmsAlert(data.sms_sent);
      setStatusMsg(
        type === "mild"
          ? "Mild anomaly started. Warning limits were crossed and a text with the technician link was sent."
          : "Breakdown started. Severe overheating and loud grinding detected."
      );
    } catch (err) {
      setStatusMsg(`Error injecting fault: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const triggerEstop = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/machines/${encodeURIComponent(machineId)}/emergency-stop`, {
        method: "POST",
      });
      const data = await res.json();
      setActiveFault("estop");
      setSmsAlert(data.sms_sent);
      setStatusMsg("Emergency stop done. Power is cut and the fan has halted. Lockout/tagout is required before any work.");
    } catch (err) {
      setStatusMsg(`Error executing E-STOP: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const resetFault = async () => {
    setLoading(true);
    try {
      await fetch(`/api/machines/${encodeURIComponent(machineId)}/reset-fault`, {
        method: "POST",
      });
      setActiveFault("nominal");
      setSmsAlert(null);
      setStatusMsg("Back to normal operation.");
    } catch (err) {
      setStatusMsg(`Error resetting: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const rpm = telemetry?.values.rotational_speed ?? telemetry?.values.spindle_speed ?? 0;
  const current = telemetry?.values.spindle_motor_current ?? 0;
  const vib = telemetry?.values.spindle_vib_rms ?? 0;
  const acoustic = telemetry?.values.acoustic_db ?? 0;
  const temp = telemetry?.values.thermal_max_c ?? telemetry?.values.process_temp ?? 0;
  const anchor = telemetry?.anchor_3d;
  const severity = telemetry?.severity ?? "normal";

  const waiting = telemetry === null; // no reading yet: show dashes instead of zeros that look like a tripped machine
  const gauges: { label: string; value: string; unit: string; tone: string; hint: string }[] = [
    {
      label: "Fan motor current",
      value: current.toFixed(1),
      unit: "A",
      tone: current === 0 ? "danger" : "",
      hint: current === 0 ? "Power tripped (0 A)" : "Normal: about 14.2 A",
    },
    {
      label: "Fan speed",
      value: String(Math.round(rpm)),
      unit: "rpm",
      tone: rpm === 0 ? "danger" : "",
      hint: rpm === 0 ? "Fan halted" : "Target: 1,750 rpm",
    },
    {
      label: "Vibration",
      value: vib.toFixed(2),
      unit: "mm/s",
      tone: vib > 4 ? "danger" : vib > 2.5 ? "warn" : "",
      hint: "Danger limit: 4.5 mm/s",
    },
    {
      label: "Acoustic noise",
      value: acoustic.toFixed(1),
      unit: "dB",
      tone: acoustic > 90 ? "danger" : acoustic > 75 ? "warn" : "",
      hint: "Grinding and squeal level",
    },
    {
      label: "Hotspot temperature",
      value: temp.toFixed(1),
      unit: "°C",
      tone: temp > 80 ? "danger" : temp > 50 ? "warn" : "",
      hint: activeFault === "estop" ? "Cooling toward 22 °C room temperature" : "Alert limit: 75 °C",
    },
  ];

  const triggers: { label: string; note: string; onClick: () => void; danger?: boolean }[] = [
    { label: "Mild anomaly", note: "Fan flutter, sends a text with the link", onClick: () => injectFault("mild") },
    { label: "Breakdown", note: "Shaft failure and overheating", onClick: () => injectFault("critical") },
    { label: "Emergency stop", note: "Cut power, fan to 0 rpm, lockout/tagout", onClick: triggerEstop, danger: true },
    { label: "Reset", note: "Back to normal operation", onClick: resetFault },
  ];

  return (
    <Panel
      title={
        <>
          Live sensor stream <span className="mono live-machine">{machineId}</span> <SimTag title="Simulated sensor feed" />
        </>
      }
      id="livestream"
      className={`livestream ${activeFault}`}
      actions={
        <span className="live-badges">
          <SeverityPill severity={severity} />
          <span className="tag">{telemetry?.phase ?? "connecting"}</span>
        </span>
      }
    >
      <div className="stack">
        <section aria-label="Demo triggers">
          <p className="eyebrow">Demo triggers</p>
          <p className="xs muted">Start a failure to see GhostShift react and send its alerts.</p>
          <div className="trigger-row">
            {triggers.map((t) => (
              <button key={t.label} type="button" className={`trigger btn ${t.danger ? "danger" : ""}`} disabled={loading} onClick={t.onClick}>
                <strong>{t.label}</strong>
                <span className="xs muted">{t.note}</span>
              </button>
            ))}
          </div>
        </section>

        {statusMsg && (
          <div className={`notice small ${activeFault === "nominal" ? "" : "warn"}`} role="status">
            <span>{statusMsg}</span>
          </div>
        )}

        <div className="gauge-grid">
          {gauges.map((g) => (
            <div key={g.label} className="gauge">
              <span className="xs muted">{g.label}</span>
              <span className={`gauge-value mono ${waiting ? "" : g.tone}`}>
                {waiting ? "—" : g.value} <span className="gauge-unit">{g.unit}</span>
              </span>
              <span className="xs muted">{waiting ? "Waiting for a reading" : g.hint}</span>
            </div>
          ))}
          <div className="gauge">
            <span className="xs muted">Camera focus</span>
            {anchor ? (
              <>
                <span className="small strong">{anchor.component}</span>
                <span className="xs mono muted">
                  [{anchor.x.toFixed(1)}, {anchor.y.toFixed(1)}, {anchor.z.toFixed(1)}] mm
                </span>
              </>
            ) : (
              <span className="small muted">Waiting for position…</span>
            )}
          </div>
        </div>

        {smsAlert && (
          <div className="sms">
            <div className="row xs">
              <span className="strong">Text sent to the technician</span>
              <span className="spacer" />
              <span className="mono muted">{new Date().toLocaleTimeString()}</span>
            </div>
            <p className="small sms-body">{smsAlert}</p>
          </div>
        )}
      </div>
    </Panel>
  );
}
