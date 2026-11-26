from __future__ import annotations

import mpmath


def ordinates(k: int, dps: int = 20) -> list:
    with mpmath.workdps(dps):
        return [mpmath.zetazero(j).imag for j in range(1, k + 1)]


def smooth_count(t):
    u = t / (2 * mpmath.pi)
    return u * mpmath.log(u / mpmath.e) + mpmath.mpf(7) / 8


def trudgian(t):
    return 0.112 * mpmath.log(t) + 0.278 * mpmath.log(mpmath.log(t)) + 2.510 + 0.2 / t


def count_bounds(t) -> tuple:
    m, e = smooth_count(t), trudgian(t)
    return m - e, m + e
