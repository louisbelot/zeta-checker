from __future__ import annotations

import math
from dataclasses import dataclass

import mpmath

EULER = float(mpmath.euler)


def sigma_table(n: int) -> list[int]:
    s = [0] * (n + 1)
    for d in range(1, n + 1):
        for m in range(d, n + 1, d):
            s[m] += d
    return s


def robin_exceptions(n: int) -> list[int]:
    s = sigma_table(n)
    c = math.exp(EULER)
    out = []
    for k in range(2, n + 1):
        bound = c * k * math.log(math.log(k))
        if abs(s[k] - bound) < 1e-9 * abs(bound):
            hit = s[k] >= mpmath.exp(mpmath.euler) * k * mpmath.log(mpmath.log(k))
        else:
            hit = s[k] >= bound
        if hit:
            out.append(k)
    return out


@dataclass(frozen=True)
class Lagarias:
    n: int
    violations: list[int]
    equal: list[int]
    tightest: int
    slack: float


def lagarias(n: int) -> Lagarias:
    s = sigma_table(n)
    h = 0.0
    violations, equal = [], []
    tightest, slack = 0, math.inf
    for k in range(1, n + 1):
        h += 1 / k
        bound = h + math.exp(h) * math.log(h)
        rel = (bound - s[k]) / bound
        if rel < 0:
            violations.append(k)
        elif rel == 0:
            equal.append(k)
        elif rel < slack:
            tightest, slack = k, rel
    return Lagarias(n, violations, equal, tightest, slack)
