from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from zeta_checker.criteria import EULER

U = 2.0**-53


def small_primes(n: int) -> np.ndarray:
    sieve = np.ones(n + 1, dtype=bool)
    sieve[:2] = False
    for p in range(2, math.isqrt(n) + 1):
        if sieve[p]:
            sieve[p * p :: p] = False
    return np.flatnonzero(sieve)


def primes_between(lo: int, hi: int, base: np.ndarray) -> np.ndarray:
    seg = np.ones(hi - lo, dtype=bool)
    for p in base:
        p = int(p)
        if p * p >= hi:
            break
        start = max(p * p, -(-lo // p) * p)
        seg[start - lo :: p] = False
    if lo < 2:
        seg[: 2 - lo] = False
    return np.flatnonzero(seg) + lo


def critical(p, k):
    p = np.asarray(p, dtype=float)
    return np.log1p((p - 1) / (p ** (k + 1) - p)) / np.log(p)


def higher_events(limit: int) -> tuple[np.ndarray, np.ndarray]:
    stop = float(critical(limit, 1))
    ps, eps = [], []
    for p in small_primes(2 * math.isqrt(limit) + 10):
        k = 2
        while (e := float(critical(p, k))) >= stop:
            ps.append(p)
            eps.append(e)
            k += 1
    order = np.argsort(eps)[::-1]
    return np.asarray(ps, dtype=float)[order], np.asarray(eps)[order]


def events(limit: int, segment: int = 2**26) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    base = small_primes(math.isqrt(limit) + 1)
    hp, he = higher_events(limit)
    j = 0
    for lo in range(0, limit + 1, segment):
        hi = min(lo + segment, limit + 1)
        p = primes_between(lo, hi, base).astype(float)
        if not len(p):
            continue
        e = critical(p, 1)
        n = j + int(np.searchsorted(-he[j:], -e[-1], side="right"))
        p, e = np.concatenate([p, hp[j:n]]), np.concatenate([e, he[j:n]])
        order = np.argsort(-e, kind="stable")
        yield p[order], e[order]
        j = n


def first(count: int, limit: int = 1000) -> list[tuple[int, float]]:
    out, n = [], 1
    for p, e in events(limit):
        for q, eq in zip(p, e, strict=True):
            n *= int(q)
            out.append((n, float(eq)))
            if len(out) == count:
                return out
    return out


RAMANUJAN = math.exp(EULER) * (2 * math.sqrt(2) - 4 - EULER + math.log(4 * math.pi))
START = math.log(5040) + 0.5


@dataclass
class Scan:
    limit: int
    count: int = 0
    log_n: float = 0.0
    lowest: tuple[float, float] = (math.inf, 0.0)
    slack: float = math.inf
    gap: float = math.inf
    error: float = 0.0
    curve: list[tuple[float, float]] = field(default_factory=list)


def scan(limit: int, points: int = 400, segment: int = 2**26) -> Scan:
    out = Scan(limit)
    log_n, L, eN, eL, last = 0.0, 0.0, 0.0, 0.0, math.inf
    grid = list(np.geomspace(START, math.log(limit) * limit, points))
    for p, e in events(limit, segment):
        out.gap = min(out.gap, float(np.min(-np.diff(np.concatenate([[last], e])) / e)))
        lp = np.log(p)
        dN, dL = np.cumsum(lp), np.cumsum(e * lp)
        k = len(p)
        eN += U * (log_n + dN[-1]) + (k + 2) * U * dN[-1]
        eL += U * (L + dL[-1]) + (k + 8) * U * dL[-1]
        ln, Ls = log_n + dN, L + dL
        log_n, L, last = float(ln[-1]), float(Ls[-1]), float(e[-1])
        ok = ln > START
        ln, Ls = ln[ok], Ls[ok]
        if not ln.size:
            continue
        lln = np.log(ln)
        m = EULER + np.log(lln) - Ls
        bound = eL + eN / (ln * lln) + 8 * U * (EULER + np.log(lln) + Ls)
        D = (math.exp(EULER) * lln - np.exp(Ls)) * np.sqrt(ln)
        i = int(np.argmin(D))
        if D[i] < out.lowest[0]:
            out.lowest = (float(D[i]), float(ln[i]))
        out.slack = min(out.slack, float(np.min(m - bound)))
        out.error = max(out.error, float(bound[-1]))
        out.count += len(ln)
        while grid and grid[0] <= ln[-1]:
            j = int(np.searchsorted(ln, grid.pop(0)))
            out.curve.append((float(ln[j]), float(D[j])))
    out.log_n = log_n
    return out
