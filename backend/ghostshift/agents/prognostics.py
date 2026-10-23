"""Prognostics agent: failure-risk score and qualified remaining-useful-life.

Risk and RUL are separate outputs with separate definitions:
- `failure_risk` is an uncalibrated score: the fraction of the baseline-to-danger
  margin projected to be consumed within the horizon on the current trend.
- `rul` is the time until the trend reaches the danger limit, reported only when
  the trend is statistically supportable, with a slope-uncertainty interval.
Components without a detected deviation get no trend RUL; their calendar-based
remaining service interval is reported separately and labelled as such.
"""

from __future__ import annotations

from ..schemas.agents import (
    DiagnosticsResult,
    FailureRisk,
    PrognosticsInput,
    PrognosticsResult,
    RulEstimate,
    SensorAssessment,
)
from ..schemas.common import DataSource, Provenance, Severity
from ..schemas.machine import (
    Component,
    ComponentHealth,
    ComponentRulEstimate,
    HealthBasis,
    LimitDirection,
    Machine,
    SensorDefinition,
    SensorRole,
)
from .diagnostics import _xy_hours
from .stats import clip, linear_fit

METHOD = "trend_extrapolation_v1"
MIN_TREND_POINTS = 12
MIN_T_STAT = 3.0
INTERVAL_K = 2.0

RISK_DEFINITION = (
    "Fraction of the baseline-to-danger-limit margin projected to be consumed within the horizon on the "
    "current linear trend. Uncalibrated heuristic score; it is not a probability of failure."
)
TREND_LIMITATIONS = [
    "Linear extrapolation assumes a constant degradation rate; bearing wear and fouling often accelerate, "
    "so the upper bound in particular may be optimistic.",
    "The threshold is a site alarm (danger) limit, not a physical failure point.",
    "Interval is ±2 standard errors of the fitted slope; it does not capture model-form uncertainty.",
]


class PrognosticsAgent:
    name = "prognostics"

    def run(self, inp: PrognosticsInput) -> PrognosticsResult:
        diag = inp.diagnostics
        machine = inp.machine
        by_sensor = {a.sensor_id: a for a in diag.sensors}
        sensors = {s.id: s for s in machine.sensors}
        upstream = inp.window.provenance.source
        simulated = upstream == DataSource.simulated

        affected = _affected_component(diag)
        candidates = self._candidate_sensors(diag, machine, affected)
        estimates = [
            e for sid in candidates
            if (e := self._estimate(inp, sensors[sid], by_sensor[sid], affected, simulated)) is not None
        ]
        supportable = [e for e in estimates if e.supportable]
        rul = min(supportable, key=lambda e: e.value_hours) if supportable else (estimates[0] if estimates else None)
        risk = self._risk(inp, candidates or _health_sensor_ids(machine), sensors, by_sensor, rul)

        limitations = list(TREND_LIMITATIONS)
        if simulated:
            limitations.append("Computed from simulated fixture telemetry; not a validated prediction.")
        if rul and not rul.supportable:
            limitations.append(rul.confidence_note)

        return PrognosticsResult(
            machine_id=machine.id,
            affected_component_id=affected,
            failure_risk=risk,
            rul=rul,
            component_health=[self._component_health(inp, c, by_sensor, sensors, rul) for c in machine.components],
            method=METHOD,
            limitations=limitations,
            provenance=Provenance(
                source=DataSource.derived,
                detail=f"GhostShift {METHOD}: OLS trend over last {inp.trend_points} samples to danger limit",
                upstream_source=upstream,
            ),
        )

    # ------------------------------------------------------------------
    def _candidate_sensors(self, diag: DiagnosticsResult, machine: Machine, affected: str | None) -> list[str]:
        """Sensors whose trend can bound the affected component's life."""
        if diag.hypotheses:
            ids = diag.hypotheses[0].signature_sensor_ids
        else:
            ids = [a.sensor_id for a in diag.anomalies]
        defs = {s.id: s for s in machine.sensors}
        return [i for i in dict.fromkeys(ids) if i in defs and defs[i].limits and defs[i].limits.danger is not None
                and defs[i].role == SensorRole.health]

    def _estimate(self, inp: PrognosticsInput, sensor: SensorDefinition, a: SensorAssessment,
                  component_id: str | None, simulated: bool) -> RulEstimate | None:
        danger = sensor.limits.danger
        sign = 1.0 if sensor.limits.direction == LimitDirection.above else -1.0
        prov = Provenance(source=DataSource.derived, detail=f"{METHOD} on {sensor.id}",
                          upstream_source=DataSource.simulated if simulated else DataSource.measured)
        base = dict(component_id=component_id or sensor.component_id, sensor_id=sensor.id, threshold=danger,
                    method=f"{METHOD}: linear trend of {sensor.name} to danger limit {danger:g} {sensor.unit}",
                    limitations=TREND_LIMITATIONS, provenance=prov)

        if not a.anomalous:
            return RulEstimate(supportable=False, value_hours=None, lower_hours=None, upper_hours=None,
                               confidence_note="No significant deviation from baseline; trend RUL not estimated.", **base)
        xs, ys = _xy_hours(inp.window.points[-inp.trend_points:], sensor.id)
        fit = linear_fit(xs, ys) if len(xs) >= MIN_TREND_POINTS else None
        if fit is None:
            return RulEstimate(supportable=False, value_hours=None, lower_hours=None, upper_hours=None,
                               confidence_note=f"Fewer than {MIN_TREND_POINTS} valid samples in trend window.", **base)
        now = fit.at(0.0)
        margin = sign * (danger - now)
        rate = sign * fit.slope
        if margin <= 0:
            return RulEstimate(supportable=True, value_hours=0.0, lower_hours=0.0, upper_hours=0.0,
                               confidence_note="Danger limit already reached on the fitted trend.", **base)
        t = rate / fit.slope_se if fit.slope_se else float("inf")
        if rate <= 0 or t < MIN_T_STAT:
            return RulEstimate(supportable=False, value_hours=None, lower_hours=None, upper_hours=None,
                               confidence_note=(f"Trend toward the limit is not statistically supportable "
                                                f"(t = {t:.1f} < {MIN_T_STAT:g}); RUL not estimated."), **base)
        hi_rate = rate + INTERVAL_K * fit.slope_se
        lo_rate = rate - INTERVAL_K * fit.slope_se
        return RulEstimate(
            supportable=True,
            value_hours=round(margin / rate, 1),
            lower_hours=round(margin / hi_rate, 1),
            upper_hours=round(margin / lo_rate, 1) if lo_rate > 0 else None,
            confidence_note=(f"Slope {fit.slope:+.4f} {sensor.unit}/h (t = {t:.1f}, n = {fit.n}); "
                             f"interval from slope ± {INTERVAL_K:g} SE" + ("" if lo_rate > 0 else "; upper bound unbounded")),
            **base,
        )

    def _risk(self, inp, sensor_ids, sensors, by_sensor, rul: RulEstimate | None) -> FailureRisk:
        h = inp.risk_horizon_hours
        score = 0.0
        for sid in sensor_ids:
            s, a = sensors.get(sid), by_sensor.get(sid)
            if not (s and a and s.limits and s.limits.danger is not None):
                continue
            sign = 1.0 if s.limits.direction == LimitDirection.above else -1.0
            span = sign * (s.limits.danger - a.baseline.mean)
            if span <= 0:
                continue
            slope = a.slope_per_hour if (rul and rul.sensor_id == sid and rul.supportable) else 0.0
            projected = a.recent_mean + slope * h
            score = max(score, clip(sign * (projected - a.baseline.mean) / span))
        band = "severe" if score >= 0.9 else "high" if score >= 0.7 else "moderate" if score >= 0.4 else "low"
        return FailureRisk(score=round(score, 3), band=band, horizon_hours=h, calibrated=False, definition=RISK_DEFINITION)

    def _component_health(self, inp: PrognosticsInput, comp: Component, by_sensor, sensors, rul) -> ComponentHealth:
        hours_since = (inp.as_of - comp.maintenance.last_service_at).total_seconds() / 3600
        remaining = comp.maintenance.service_interval_hours - hours_since
        interval = ComponentRulEstimate(
            value_hours=round(remaining, 0),
            unit="hours",
            method="maintenance_interval",
            supportable=True,
            basis_note=(f"Service interval {comp.maintenance.service_interval_hours:g} h minus calendar hours since "
                        f"last service ({comp.maintenance.last_service_at.date()}). Schedule-based, not condition-based."),
            provenance=comp.maintenance.provenance,
        )
        mine = [by_sensor[s.id] for s in inp.machine.sensors
                if s.component_id == comp.id and s.role == SensorRole.health and s.id in by_sensor]
        if not mine:
            return ComponentHealth(component_id=comp.id, status=Severity.normal, health_score=None,
                                   basis=HealthBasis.interval_only,
                                   summary="No sensors; schedule only.",
                                   rul=None, remaining_service_interval=interval)
        status = max((a.severity for a in mine), key=lambda s: s.rank)
        consumed = 0.0
        for a in mine:
            s = sensors[a.sensor_id]
            if s.limits and s.limits.danger is not None:
                sign = 1.0 if s.limits.direction == LimitDirection.above else -1.0
                span = sign * (s.limits.danger - a.baseline.mean)
                if span > 0:
                    consumed = max(consumed, clip(sign * (a.recent_mean - a.baseline.mean) / span))
        worst = max(mine, key=lambda a: (a.severity.rank, abs(a.z_score)))
        summary = (f"{worst.sensor_name.split(' (')[0]} {worst.current_value:.3g} {worst.unit} "
                   f"({(worst.current_value - worst.baseline.mean) / abs(worst.baseline.mean or 1) * 100:+.0f}% vs normal)" if status != Severity.normal else "Readings normal")

        comp_rul = None
        if rul and rul.component_id == comp.id:
            comp_rul = ComponentRulEstimate(
                value_hours=rul.value_hours, lower_hours=rul.lower_hours, upper_hours=rul.upper_hours,
                method=METHOD, supportable=rul.supportable, basis_note=rul.confidence_note, provenance=rul.provenance,
            )
        else:
            note = ("No degradation trend detected; trend-based RUL not estimated." if status == Severity.normal
                    else f"Deviation attributed to the fault signature on {rul.component_id}; see that estimate."
                    if rul else "Deviation detected but no supportable trend estimate.")
            comp_rul = ComponentRulEstimate(
                value_hours=None, method=METHOD, supportable=False, basis_note=note,
                provenance=Provenance(source=DataSource.derived, detail=METHOD, upstream_source=inp.window.provenance.source),
            )
        return ComponentHealth(component_id=comp.id, status=status, health_score=round(1 - consumed, 3),
                               basis=HealthBasis.sensor, summary=summary, rul=comp_rul,
                               remaining_service_interval=interval)


def _affected_component(diag: DiagnosticsResult) -> str | None:
    if diag.hypotheses:
        return diag.hypotheses[0].component_id
    if diag.anomalies:
        return diag.anomalies[0].component_id
    return None


def _health_sensor_ids(machine: Machine) -> list[str]:
    return [s.id for s in machine.sensors if s.role == SensorRole.health]
