from __future__ import annotations

import math
from dataclasses import dataclass

import mpmath

from . import zeros

EULER = float(mpmath.euler)


def xi(s):
    return s * (s - 1) / 2 * mpmath.pi ** (-s / 2) * mpmath.gamma(s / 2) * mpmath.zeta(s)


def log_xi(s):
    return mpmath.log(xi(s))


def log_gamma_factor(s):
    return -s / 2 * mpmath.log(mpmath.pi) + mpmath.loggamma(1 + s / 2)


def keiper(logf, n: int, r: float = 0.8, m: int = 512, dps: int = 30) -> list[float]:
    if not 0 < r < 1 or m <= 2 * n:
        raise ValueError("need 0 < r < 1 and more than 2n points")
    with mpmath.workdps(dps):
        tau = 2 * mpmath.pi
        g = []
        for k in range(m):
            z = r * mpmath.expjpi(mpmath.mpf(2 * k) / m)
            v = logf(1 / (1 - z))
            if g:
                v += 1j * tau * round(float((g[-1] - v).imag / tau))
            g.append(v)
        if abs(float((g[0] - g[-1]).imag)) > 1:
            raise ValueError("the log winds around the contour: a zero inside |z| < r")
        out = []
        for j in range(1, n + 1):
            a = mpmath.fsum(v * mpmath.expjpi(-mpmath.mpf(2 * k * j) / m) for k, v in enumerate(g))
            out.append(float((j * a / (m * mpmath.mpf(r) ** j)).real))
    return out


def li_coefficients(n: int, r: float = 0.8, m: int = 512, dps: int = 30) -> list[float]:
    return keiper(log_xi, n, r, m, dps)


def archimedean(n: int) -> float:
    with mpmath.workdps(30 + n // 3):
        g, pi = mpmath.euler, mpmath.pi
        s = 1 - n * (g + mpmath.log(pi) + 2 * mpmath.log(2)) / 2
        s += mpmath.fsum(
            (-1) ** k * mpmath.binomial(n, k) * (1 - mpmath.mpf(2) ** -k) * mpmath.zeta(k)
            for k in range(2, n + 1)
        )
        return float(s)


def voros(n: int) -> float:
    return n / 2 * (math.log(n / (2 * math.pi)) + EULER - 1)


@dataclass(frozen=True)
class ZeroSum:
    n: int
    zeros: int
    height: float
    partial: float
    tail: float
    upper: float

    @property
    def estimate(self) -> float:
        return self.partial + self.tail


def _term(n, t):
    return 4 * mpmath.sin(n * mpmath.atan(1 / (2 * t))) ** 2


def _density(t):
    return mpmath.log(t / (2 * mpmath.pi)) / (2 * mpmath.pi)


def from_zeros(n: int, gammas: list) -> ZeroSum:
    k = len(gammas) - 1
    if k < 1:
        raise ValueError("need at least two zeros")
    with mpmath.workdps(20):
        T = (gammas[k - 1] + gammas[k]) / 2
        if 2 * n * mpmath.atan(1 / (2 * T)) > mpmath.pi:
            raise ValueError("n too large for the height: the tail terms are not monotone")
        partial = mpmath.fsum(_term(n, g) for g in gammas[:k])
        cuts = [T, 2 * T, 10 * T, mpmath.inf]
        tail = mpmath.quad(lambda t: _term(n, t) * _density(t), cuts)
        tail += _term(n, T) * (zeros.smooth_count(T) - k)

        def slope(t):
            return 8 * n * mpmath.sin(2 * n * mpmath.atan(1 / (2 * t))) / (4 * t * t + 1)

        upper = mpmath.quad(lambda t: (zeros.count_bounds(t)[1] - k) * slope(t), cuts)
    return ZeroSum(n, k, float(T), float(partial), float(tail), float(upper))
