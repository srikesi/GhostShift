import { useEffect, useState, useRef } from "react";
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
          ? "⚠️ Mild Anomaly Injected — Warning thresholds crossed. Twilio SMS dispatched with inspection link for human call."
          : "🚨 Catastrophic Breakdown Injected — High thermal runaway & severe acoustic screeching detected!"
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
      setStatusMsg("🛑 AUTONOMOUS E-STOP EXECUTED — Power cut to 0A, Fan halted at 0 RPM. Mandatory LOTO required.");
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
      setStatusMsg("✅ Equipment Restored — Normal Cold-Aisle Operating Parameters Active.");
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

  return (
    <div className={`livestream-card ${activeFault}`}>
      <div className="livestream-header">
        <div className="livestream-title">
          <span className="live-pulse-dot" />
          <span className="live-label">LIVE SENSOR STREAM</span>
          <span className="live-machine-tag">{machineId}</span>
        </div>
        <div className="livestream-status-badge">
          <span className={`status-pill ${severity}`}>
            {severity.toUpperCase()}
          </span>
          <span className="phase-pill">{telemetry?.phase ?? "CONNECTING"}</span>
        </div>
      </div>

      {/* Interactive Trigger Controls */}
      <div className="break-controls-banner">
        <div className="break-controls-label">
          <span>OPERATIONAL DEMO TRIGGERS</span>
          <span className="break-subtitle">Inject live failures to test agent orchestration & Twilio alerts</span>
        </div>
        <div className="break-buttons-row">
          <button
            type="button"
            className="btn-trigger mild"
            disabled={loading}
            onClick={() => injectFault("mild")}
          >
            <span className="btn-icon">⚡</span>
            <div className="btn-text-wrap">
              <strong>Break: Mild Anomaly</strong>
              <small>Flutter / SMS human link</small>
            </div>
          </button>

          <button
            type="button"
            className="btn-trigger critical"
            disabled={loading}
            onClick={() => injectFault("critical")}
          >
            <span className="btn-icon">💥</span>
            <div className="btn-text-wrap">
              <strong>Break: Catastrophic Trip</strong>
              <small>Shaft breakdown / Overheat</small>
            </div>
          </button>

          <button
            type="button"
            className="btn-trigger estop"
            disabled={loading}
            onClick={triggerEstop}
          >
            <span className="btn-icon">🛑</span>
            <div className="btn-text-wrap">
              <strong>Emergency E-STOP</strong>
              <small>Cut power 0A / 0 RPM / LOTO</small>
            </div>
          </button>

          <button
            type="button"
            className="btn-trigger reset"
            disabled={loading}
            onClick={resetFault}
          >
            <span className="btn-icon">↺</span>
            <div className="btn-text-wrap">
              <strong>Reset Baseline</strong>
              <small>Restore nominal health</small>
            </div>
          </button>
        </div>
      </div>

      {/* Status or Alert Notification Banner */}
      {statusMsg && (
        <div className={`live-feedback-banner ${activeFault}`}>
          <span>{statusMsg}</span>
        </div>
      )}

      {/* Live Digital Readout Gauges */}
      <div className="telemetry-gauges-grid">
        <div className="gauge-box">
          <span className="gauge-label">FAN / MOTOR CURRENT</span>
          <div className="gauge-value-wrap">
            <span className={`gauge-value ${current === 0 ? "zero-cut" : ""}`}>
              {current.toFixed(1)}
            </span>
            <span className="gauge-unit">A</span>
          </div>
          <span className="gauge-hint">{current === 0 ? "POWER TRIPPED (0A)" : "Normal nominal: 14.2 A"}</span>
        </div>

        <div className="gauge-box">
          <span className="gauge-label">FAN / SHAFT SPEED</span>
          <div className="gauge-value-wrap">
            <span className={`gauge-value ${rpm === 0 ? "zero-cut" : ""}`}>
              {Math.round(rpm)}
            </span>
            <span className="gauge-unit">RPM</span>
          </div>
          <span className="gauge-hint">{rpm === 0 ? "IMPELLER HALTED" : "Operating target: 1,750 RPM"}</span>
        </div>

        <div className="gauge-box">
          <span className="gauge-label">VIBRATION RMS</span>
          <div className="gauge-value-wrap">
            <span className={`gauge-value ${vib > 4.0 ? "danger" : vib > 2.5 ? "warn" : ""}`}>
              {vib.toFixed(2)}
            </span>
            <span className="gauge-unit">mm/s</span>
          </div>
          <span className="gauge-hint">Danger threshold: 4.5 mm/s</span>
        </div>

        <div className="gauge-box">
          <span className="gauge-label">ACOUSTIC NOISE (12LABS)</span>
          <div className="gauge-value-wrap">
            <span className={`gauge-value ${acoustic > 90 ? "danger" : acoustic > 75 ? "warn" : ""}`}>
              {acoustic.toFixed(1)}
            </span>
            <span className="gauge-unit">dB</span>
          </div>
          <span className="gauge-hint">Audio chattering squeal index</span>
        </div>

        <div className="gauge-box">
          <span className="gauge-label">HOTSPOT TEMP (NOVA IR)</span>
          <div className="gauge-value-wrap">
            <span className={`gauge-value ${temp > 80 ? "danger" : temp > 50 ? "warn" : ""}`}>
              {temp.toFixed(1)}
            </span>
            <span className="gauge-unit">°C</span>
          </div>
          <span className="gauge-hint">{activeFault === "estop" ? "Dissipating to 22°C ambient" : "Alert limit: 75.0 °C"}</span>
        </div>

        <div className="gauge-box anchor-box">
          <span className="gauge-label">3D SPATIAL ANCHOR</span>
          <div className="anchor-coord-text">
            {anchor ? (
              <>
                <strong>{anchor.component}</strong>
                <code>[{anchor.x.toFixed(1)}, {anchor.y.toFixed(1)}, {anchor.z.toFixed(1)}] mm</code>
              </>
            ) : (
              <span>Tracking machine coordinates...</span>
            )}
          </div>
          <span className="gauge-hint">Target camera vector for Three.js</span>
        </div>
      </div>

      {/* Dispatched Twilio SMS Terminal */}
      {smsAlert && (
        <div className="sms-dispatch-terminal">
          <div className="sms-terminal-header">
            <span className="terminal-dot green" />
            <span>TWILIO CELLULAR / WHATSAPP DISPATCH FEED</span>
            <span className="timestamp">{new Date().toLocaleTimeString()}</span>
          </div>
          <div className="sms-terminal-body">
            <code>{smsAlert}</code>
          </div>
        </div>
      )}
    </div>
  );
}
