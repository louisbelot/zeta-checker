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


def vasyunin(h: int, k: int):
    return mpmath.fsum(
        mpmath.frac(mpmath.mpf(a * h) / k) * mpmath.cot(mpmath.pi * a / k) for a in range(1, k)
    )


def gram(h: int, k: int):
    d = math.gcd(h, k)
    h, k = h // d, k // d
    c = (mpmath.log(2 * mpmath.pi) - mpmath.euler) / 2 * (mpmath.mpf(1) / h + mpmath.mpf(1) / k)
    c += mpmath.mpf(k - h) / (2 * h * k) * mpmath.log(mpmath.mpf(h) / k)
    c -= mpmath.pi / (2 * h * k) * (vasyunin(h, k) + vasyunin(k, h))
    return c / d


def chi_dot(k: int):
    return (1 - mpmath.euler + mpmath.log(k)) / k


def baez_duarte(n: int, dps: int = 40) -> list[float]:
    with mpmath.workdps(dps):
        L, y, out = [], [], []
        dist = mpmath.mpf(1)
        for i in range(n):
            row = []
            for j in range(i):
                dot = mpmath.fsum(row[t] * L[j][t] for t in range(j))
                row.append((gram(i + 1, j + 1) - dot) / L[j][j])
            diag = gram(i + 1, i + 1) - mpmath.fsum(a * a for a in row)
            if diag <= 0:
                raise ValueError(f"Gram matrix not positive definite at N = {i + 1}")
            row.append(mpmath.sqrt(diag))
            L.append(row)
            dot = mpmath.fsum(row[t] * y[t] for t in range(i))
            y.append((chi_dot(i + 1) - dot) / row[i])
            dist -= y[i] ** 2
            out.append(float(dist))
    return out
