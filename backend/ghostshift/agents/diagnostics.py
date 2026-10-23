"""Diagnostics agent: baseline-relative anomaly assessment and fault signatures.

Deterministic. Compares each sensor's recent behaviour with the machine's own
baseline window, checks configured alarm limits, and matches rule-based fault
signatures from `fixtures/fault_modes.json`.
"""

from __future__ import annotations

from typing import Callable

from ..schemas.agents import (
    Anomaly,
    Baseline,
    DiagnosticsInput,
    DiagnosticsResult,
    EvidenceRef,
    FaultHypothesis,
    LimitState,
    SensorAssessment,
)
from ..schemas.common import DataSource, Provenance, Severity
from ..schemas.machine import LimitDirection, SensorDefinition, SensorRole
from ..schemas.reference import FaultMode, SignatureCondition
from ..schemas.telemetry import TelemetryPoint
from .stats import linear_fit, mean, std

METHOD = "baseline_zscore_v1"
Z_WATCH = 3.0
PERSIST_SIGMA = 2.0
PERSIST_FRACTION = 0.6
MIN_BASELINE = 30
LIMIT_SMOOTHING = 3
TREND_POINTS = 24


class DiagnosticsAgent:
    name = "diagnostics"

    def __init__(self, fault_modes_for: Callable[[str], list[FaultMode]]):
        self._fault_modes_for = fault_modes_for

    def run(self, inp: DiagnosticsInput) -> DiagnosticsResult:
        points = inp.window.points
        if not points:
            raise ValueError("Telemetry window is empty")
        base_pts = [p for p in points if inp.baseline_start_index <= p.index <= inp.baseline_end_index]
        recent_pts = points[-inp.recent_points:]
        warnings: list[str] = []
        if points[-1].index <= inp.baseline_end_index:
            warnings.append("Analysis window overlaps the baseline window; deviations cannot be assessed yet.")
        if inp.window.provenance.source == DataSource.simulated:
            warnings.append("Telemetry is simulated fixture data.")
        warnings += [f"Unavailable from source: {f}" for f in inp.window.unavailable_fields]

        assessments: list[SensorAssessment] = []
        anomalies: list[Anomaly] = []
        evidence: list[EvidenceRef] = []
        for sensor in inp.machine.sensors:
            a = self._assess(sensor, base_pts, recent_pts, points, warnings)
            if a is None:
                continue
            assessments.append(a)
            if sensor.role == SensorRole.context and abs(a.z_score) >= Z_WATCH:
                warnings.append(
                    f"Operating context changed: {sensor.name} is {a.z_score:+.1f}σ from baseline; "
                    "deviations on other sensors may reflect duty, not condition."
                )
            if a.anomalous:
                ev = _evidence(sensor, recent_pts, a)
                evidence.append(ev)
                anomalies.append(
                    Anomaly(
                        sensor_id=sensor.id,
                        component_id=sensor.component_id,
                        severity=a.severity,
                        description=_describe(sensor, a),
                        evidence_id=ev.id,
                    )
                )

        hypotheses = self._match_fault_modes(inp.machine.machine_type, {a.sensor_id: a for a in assessments})
        severity = max((a.severity for a in assessments), key=lambda s: s.rank, default=Severity.normal)
        return DiagnosticsResult(
            machine_id=inp.machine.id,
            analyzed_start_index=points[0].index,
            analyzed_end_index=points[-1].index,
            severity=severity,
            sensors=assessments,
            anomalies=sorted(anomalies, key=lambda x: -x.severity.rank),
            hypotheses=hypotheses,
            evidence=evidence,
            warnings=warnings,
            method=METHOD,
            provenance=Provenance(
                source=DataSource.derived,
                detail=f"GhostShift {METHOD}: baseline z-score, persistence, alarm limits, rule signatures",
                upstream_source=inp.window.provenance.source,
            ),
        )

    # ------------------------------------------------------------------
    def _assess(self, sensor: SensorDefinition, base_pts, recent_pts, all_pts, warnings) -> SensorAssessment | None:
        base = _values(base_pts, sensor.id)
        recent = _values(recent_pts, sensor.id)
        if len(base) < 3 or not recent:
            warnings.append(f"{sensor.name}: insufficient data for assessment.")
            return None
        if len(base) < MIN_BASELINE:
            warnings.append(f"{sensor.name}: baseline has only {len(base)} samples (< {MIN_BASELINE}).")
        b_mean = mean(base)
        b_std = max(std(base), 1e-6, abs(b_mean) * 0.002)
        r_mean = mean(recent)
        z = (r_mean - b_mean) / b_std
        missing = sum(1 for p in all_pts if p.values.get(sensor.id) is None)

        sign = 1 if z >= 0 else -1
        beyond = sum(1 for v in recent if sign * (v - b_mean) / b_std > PERSIST_SIGMA)
        sustained = abs(z) >= Z_WATCH and beyond / len(recent) >= PERSIST_FRACTION

        trend_pts = all_pts[-TREND_POINTS:]
        xs, ys = _xy_hours(trend_pts, sensor.id)
        fit = linear_fit(xs, ys)
        slope = fit.slope if fit else 0.0

        smoothed = mean(recent[-LIMIT_SMOOTHING:])
        limit_state = LimitState.no_limits
        alert = danger = None
        if sensor.limits:
            alert, danger = sensor.limits.alert, sensor.limits.danger
            above = sensor.limits.direction == LimitDirection.above
            exceeds = (lambda lim: lim is not None and (smoothed >= lim if above else smoothed <= lim))
            limit_state = LimitState.danger if exceeds(danger) else LimitState.alert if exceeds(alert) else LimitState.normal

        if sensor.role == SensorRole.context:
            severity = Severity.normal
        elif limit_state == LimitState.danger:
            severity = Severity.critical
        elif limit_state == LimitState.alert:
            severity = Severity.warning
        elif sustained:
            severity = Severity.watch
        else:
            severity = Severity.normal

        return SensorAssessment(
            sensor_id=sensor.id,
            sensor_name=sensor.name,
            component_id=sensor.component_id,
            unit=sensor.unit,
            role=sensor.role.value,
            baseline=Baseline(
                start_index=base_pts[0].index, end_index=base_pts[-1].index, mean=round(b_mean, 4),
                std=round(b_std, 4), n=len(base),
            ),
            recent_mean=round(r_mean, 4),
            current_value=round(smoothed, 4),
            latest_value=round(recent[-1], 4),
            z_score=round(z, 2),
            pct_change=round((r_mean - b_mean) / abs(b_mean) * 100 if b_mean else 0.0, 2),
            slope_per_hour=round(slope, 5),
            limit_state=limit_state,
            alert_limit=alert,
            danger_limit=danger,
            anomalous=severity.rank >= Severity.watch.rank,
            severity=severity,
            missing_points=missing,
        )

    def _match_fault_modes(self, machine_type: str, by_sensor: dict[str, SensorAssessment]) -> list[FaultHypothesis]:
        out = []
        for fm in self._fault_modes_for(machine_type):
            if not all(_holds(c, by_sensor) for c in fm.required):
                continue
            supporting = [c for c in fm.supporting if _holds(c, by_sensor)]
            contra = [c for c in fm.contra if _holds(c, by_sensor)]
            frac = len(supporting) / len(fm.supporting) if fm.supporting else 1.0
            confidence = max(0.0, min(0.95, 0.5 + 0.4 * frac - 0.25 * len(contra)))
            out.append(
                FaultHypothesis(
                    fault_mode_id=fm.id,
                    name=fm.name,
                    component_id=fm.component_id,
                    signature_sensor_ids=[c.sensor for c in fm.required if c.direction != "stable"],
                    confidence=round(confidence, 2),
                    confidence_method="Rule signature score: 0.5 if required conditions hold, +0.4 × supporting fraction, −0.25 per contra (heuristic, uncalibrated)",
                    matched_conditions=[c.describe() for c in fm.required + supporting],
                    unmatched_conditions=[c.describe() for c in fm.supporting if c not in supporting],
                    contradicting_conditions=[c.describe() for c in contra],
                )
            )
        return sorted(out, key=lambda h: -h.confidence)


def _holds(c: SignatureCondition, by_sensor: dict[str, SensorAssessment]) -> bool:
    a = by_sensor.get(c.sensor)
    if a is None:
        return False
    if c.direction == "up":
        return a.z_score >= (c.min_z or 0)
    if c.direction == "down":
        return a.z_score <= -(c.min_z or 0)
    return abs(a.z_score) < (c.max_abs_z or 0)


def _values(pts: list[TelemetryPoint], sid: str) -> list[float]:
    return [v for p in pts if (v := p.values.get(sid)) is not None]


def _xy_hours(pts: list[TelemetryPoint], sid: str) -> tuple[list[float], list[float]]:
    if not pts:
        return [], []
    t_end = pts[-1].timestamp
    xs, ys = [], []
    for p in pts:
        v = p.values.get(sid)
        if v is not None:
            xs.append((p.timestamp - t_end).total_seconds() / 3600.0)
            ys.append(v)
    return xs, ys


def _evidence(sensor: SensorDefinition, recent_pts: list[TelemetryPoint], a: SensorAssessment) -> EvidenceRef:
    s, e = recent_pts[0], recent_pts[-1]
    return EvidenceRef(
        id=f"EV-{sensor.id}-{s.index}-{e.index}",
        sensor_id=sensor.id,
        start_index=s.index,
        end_index=e.index,
        start_time=s.timestamp,
        end_time=e.timestamp,
        description=(
            f"Mean {a.recent_mean:g} {sensor.unit} over samples {s.index}–{e.index} vs baseline "
            f"{a.baseline.mean:g} ± {a.baseline.std:g} {sensor.unit} (samples {a.baseline.start_index}–{a.baseline.end_index})"
        ),
    )


def _describe(sensor: SensorDefinition, a: SensorAssessment) -> str:
    ratio = a.current_value / a.baseline.mean if a.baseline.mean else 0
    parts = [f"{sensor.name} at {a.current_value:.2f} {sensor.unit}, {a.z_score:+.1f}σ vs baseline ({ratio:.2f}× baseline mean)"]
    if a.limit_state in (LimitState.alert, LimitState.danger):
        lim = a.danger_limit if a.limit_state == LimitState.danger else a.alert_limit
        parts.append(f"{a.limit_state.value} limit {lim:g} {sensor.unit} exceeded")
    if a.slope_per_hour:
        parts.append(f"trend {a.slope_per_hour:+.3f} {sensor.unit}/h")
    return "; ".join(parts)
