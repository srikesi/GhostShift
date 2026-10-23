"""Small numeric helpers (no numpy dependency needed for the demo sizes)."""

from __future__ import annotations

import math
from dataclasses import dataclass


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    slope_se: float
    n: int

    def at(self, x: float) -> float:
        return self.intercept + self.slope * x

    @property
    def t_stat(self) -> float:
        if self.slope_se == 0:
            return math.inf if self.slope != 0 else 0.0
        return self.slope / self.slope_se


def linear_fit(xs: list[float], ys: list[float]) -> LinearFit | None:
    """Ordinary least squares y = a + b x with the standard error of b."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    s2 = resid / (n - 2)
    return LinearFit(slope=b, intercept=a, slope_se=math.sqrt(s2 / sxx), n=n)


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
