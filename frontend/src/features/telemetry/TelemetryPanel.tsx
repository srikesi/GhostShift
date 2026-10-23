import type { DiagnosticsResult, Machine, Severity, TelemetryResponse } from "../../api/types";
import { Icon, Panel, SimTag } from "../../components/ui";
import { fmtDateTime } from "../../lib/format";
import { SensorChart } from "./SensorChart";
import "./telemetry.css";

interface ReplayProps {
  playing: boolean;
  busy: boolean;
  onPlay: () => void;
  onPause: () => void;
  onStep: () => void;
  onJump: () => void;
  onEnd: () => void;
  onReset: () => void;
  onSeek: (cursor: number) => void;
}

export function TelemetryPanel({
  machine,
  telemetry,
  screening,
  replay,
}: {
  machine: Machine;
  telemetry: TelemetryResponse;
  screening: DiagnosticsResult;
  replay: ReplayProps;
}) {
  const byId = Object.fromEntries(screening.sensors.map((a) => [a.sensor_id, a]));
  const rank = (id: string, role: string) => (role === "context" ? 10 : 0) - (byId[id]?.anomalous ? 5 : 0);
  const sensors = [...machine.sensors].sort((a, b) => rank(a.id, a.role) - rank(b.id, b.role));

  return (
    <Panel
      title="Sensors"
      id="telemetry"
      actions={telemetry.window.provenance.source === "simulated" ? <SimTag title={telemetry.window.provenance.detail} /> : null}
      bodyClass="panel-body telemetry-body"
    >
      <ReplayBar telemetry={telemetry} {...replay} />
      <div className="sensor-grid">
        {sensors.map((s) => (
          <SensorChart
            key={s.id}
            sensor={s}
            points={telemetry.window.points}
            length={telemetry.length}
            assessment={byId[s.id]}
          />
        ))}
      </div>
      {telemetry.window.unavailable_fields.length > 0 && (
        <p className="xs muted">Not in this data source: {telemetry.window.unavailable_fields.join(", ")}</p>
      )}
    </Panel>
  );
}

const SEG_CLASS: Record<Severity, string> = { normal: "ok", watch: "watch", warning: "warning", critical: "critical" };

function ReplayBar({ telemetry, playing, busy, onPlay, onPause, onStep, onJump, onEnd, onReset, onSeek }: ReplayProps & { telemetry: TelemetryResponse }) {
  const n = telemetry.length;
  const pct = (i: number) => `${(i / (n - 1)) * 100}%`;
  const atEnd = telemetry.cursor >= n - 1;
  const now = telemetry.window.points[telemetry.window.points.length - 1]?.timestamp;
  const faultStart = telemetry.scenario_phases[1]?.start_index;

  return (
    <div className="replay">
      <div className="replay-controls">
        {playing ? (
          <button className="btn primary" onClick={onPause}>
            <Icon name="pause" /> Pause
          </button>
        ) : (
          <button className="btn primary" onClick={onPlay} disabled={atEnd}>
            <Icon name="play" /> Play
          </button>
        )}
        <button className="btn" onClick={onStep} disabled={playing || busy || atEnd} title="Forward 1 hour">
          <Icon name="step" /> 1 h
        </button>
        <button className="btn" onClick={onJump} disabled={playing || busy}>
          <Icon name="jump" /> Skip to fault
        </button>
        <button className="btn ghost" onClick={onEnd} disabled={playing || busy || atEnd} title="Skip to end" aria-label="Skip to end">
          <Icon name="end" />
        </button>
        <button className="btn ghost" onClick={onReset} disabled={busy} title="Back to start" aria-label="Back to start">
          <Icon name="reset" />
        </button>
        <span className="spacer" />
        <span className="mono small replay-clock">{now ? fmtDateTime(now) : "—"}</span>
      </div>

      <div
        className="track"
        role="slider"
        tabIndex={0}
        aria-label="Replay position"
        aria-valuemin={telemetry.baseline_end_index + 1}
        aria-valuemax={n - 1}
        aria-valuenow={telemetry.cursor}
        onClick={(e) => {
          if (playing) return;
          const r = e.currentTarget.getBoundingClientRect();
          onSeek(Math.round(((e.clientX - r.left) / r.width) * (n - 1)));
        }}
        onKeyDown={(e) => {
          if (playing) return;
          if (e.key === "ArrowRight") onSeek(telemetry.cursor + 4);
          if (e.key === "ArrowLeft") onSeek(telemetry.cursor - 4);
        }}
      >
        <span className="seg learn" style={{ left: 0, width: pct(telemetry.baseline_end_index + 1) }} title="Used to learn normal behaviour" />
        {telemetry.detection_segments.map((s) => (
          <span
            key={s.start_index}
            className={`seg ${SEG_CLASS[s.severity]}`}
            style={{ left: pct(s.start_index), width: pct(s.end_index - s.start_index + 1) }}
          />
        ))}
        {faultStart !== undefined && (
          <span className="fault-mark" style={{ left: pct(faultStart) }} title="Simulated fault starts here (hidden from GhostShift)" />
        )}
        <span className="cursor" style={{ left: pct(telemetry.cursor) }} aria-hidden />
      </div>

      <div className="legend xs muted" aria-hidden>
        <span><i className="sw learn" /> Learning normal</span>
        <span><i className="sw watch" /> Watch</span>
        <span><i className="sw warning" /> Warning</span>
        <span><i className="sw critical" /> Critical</span>
        <span className="spacer" />
        <span><i className="sw band" /> Normal range</span>
        <span><i className="sw dash-amber" /> Alert limit</span>
        <span><i className="sw dash-red" /> Danger limit</span>
      </div>
    </div>
  );
}
