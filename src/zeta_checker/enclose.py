from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

import mpmath
from mpmath import iv

FIRST_ORDINATE = 14


def box(rad):
    e = iv.mpf([-rad.b, rad.b])
    return iv.mpc(e, e)


def bernoulli(k: int):
    p, q = mpmath.bernfrac(k)
    return iv.mpf(p) / q


def npow(k: int, s):
    return iv.exp(-s * iv.log(iv.mpf(k)))


def zeta(s, n: int = 20, m: int = 12):
    total = sum((npow(k, s) for k in range(2, n)), iv.mpc(1))
    ns = npow(n, s)
    total += n * ns / (s - 1) + ns / 2
    poch, fact = s, iv.mpf(2)
    for k in range(1, m + 1):
        total += bernoulli(2 * k) / fact * poch * ns / iv.mpf(n) ** (2 * k - 1)
        poch *= (s + 2 * k - 1) * (s + 2 * k)
        fact *= (2 * k + 1) * (2 * k + 2)
    sigma = s.real.a + 2 * m + 1
    if sigma <= 0:
        raise ValueError("Euler-Maclaurin needs re s > -(2m + 1)")
    first = abs(bernoulli(2 * m + 2) / fact * poch * ns / iv.mpf(n) ** (2 * m + 1))
    return total + box(first * abs(s + 2 * m + 1) / sigma)


def log_gamma_stirling(w, m: int = 12):
    if w.real.a <= 0:
        raise ValueError("Stirling needs re w > 0")
    out = (w - iv.mpf(1) / 2) * iv.log(w) - w + iv.log(2 * iv.pi) / 2
    for k in range(1, m):
        out += bernoulli(2 * k) / (2 * k * (2 * k - 1) * w ** (2 * k - 1))
    r = abs(w)
    sec2 = 2 * r / (r + w.real)
    bound = abs(bernoulli(2 * m)) / (2 * m * (2 * m - 1) * r ** (2 * m - 1)) * sec2**m
    return out + box(bound)


def gamma(w, shift: int = 20):
    den = iv.mpc(1)
    for j in range(shift):
        den *= w + j
    return iv.exp(log_gamma_stirling(w + shift)) / den


def xi(s):
    return s * (s - 1) / 2 * iv.exp(-s / 2 * iv.log(iv.pi)) * gamma(s / 2) * zeta(s)


def sum_inverse_square_ordinates():
    a = iv.mpf(FIRST_ORDINATE)
    la, tau = iv.log(a), 2 * iv.pi
    main = ((la + 1) / a - iv.log(tau * iv.e) / a) / tau
    rest = (iv.mpf(7) / 8 + iv.mpf("2.510")) / (2 * a**2)
    rest += (iv.mpf("0.112") + iv.mpf("0.278")) * (2 * la + 1) / (4 * a**2)
    rest += iv.mpf("0.2") / (3 * a**3)
    return 2 * (main + rest)


@dataclass(frozen=True)
class Enclosure:
    n: int
    lo: mpmath.mpf
    hi: mpmath.mpf
    aliasing: mpmath.mpf

    @property
    def width(self):
        return self.hi - self.lo

    def decimals(self, digits: int) -> tuple[str, str]:
        return outward(self.lo, digits, False), outward(self.hi, digits, True)


def outward(x, digits: int, up: bool) -> str:
    q = Fraction(*x.as_integer_ratio()) * 10**digits
    v = math.ceil(q) if up else math.floor(q)
    return str(Decimal(v).scaleb(-digits))


def li_enclosures(n: int, r: str = "0.8", m: int = 512, dps: int = 30) -> list[Enclosure]:
    if m <= 2 * n:
        raise ValueError("need more than 2n points")
    old = iv.dps
    iv.dps = dps
    try:
        return _enclose(n, iv.mpf(r), m)
    finally:
        iv.dps = old


def _enclose(n: int, r, m: int) -> list[Enclosure]:
    g = iv.euler
    lam1 = 1 + g / 2 - iv.log(4 * iv.pi) / 2
    s2 = sum_inverse_square_ordinates()
    grow = iv.exp(iv.mpf(1) / FIRST_ORDINATE)
    y = r * grow
    if y.b >= 1:
        raise ValueError(f"radius too large: need r < exp(-1/{FIRST_ORDINATE})")
    slope = lam1 / (1 - r) ** 2 + s2 * grow * (1 + y) / (1 - y) ** 3
    step = (slope * 2 * iv.pi * r / m).b

    tau = 2 * iv.pi
    nodes = [iv.cos(tau * k / m) + iv.mpc(0, 1) * iv.sin(tau * k / m) for k in range(m)]
    values = []
    phase = mpmath.mpf(0)
    for k in range(m):
        f = xi(1 / (1 - r * nodes[k]))
        if values:
            prev = values[-1].imag
            if (prev.b - prev.a) / 2 + step >= mpmath.pi / 2:
                raise ValueError("samples too far apart to follow the branch of log xi")
            phase = prev.mid.a
        turn = iv.cos(phase) - iv.mpc(0, 1) * iv.sin(phase)
        w = f * turn
        if w.real.a <= 0:
            raise ValueError("enclosure of xi too wide to take its log")
        values.append(iv.log(w) + iv.mpc(0, phase))

    x, q = r**m, y**m
    out = []
    for j in range(1, n + 1):
        acc = iv.mpc(0)
        for k, v in enumerate(values):
            acc += v * nodes[(-k * j) % m]
        lam = j * acc / (m * r**j)
        if not lam.imag.a <= 0 <= lam.imag.b:
            raise ValueError(f"imaginary part of lambda_{j} excludes zero")
        alias = j * (lam1 * x / (1 - x) + s2 * grow**j * (j * q / (1 - q) + m * q / (1 - q) ** 2))
        with mpmath.workdps(iv.dps):
            lo, hi = mpmath.mpf((lam.real - alias).a), mpmath.mpf((lam.real + alias).b)
            out.append(Enclosure(j, lo, hi, mpmath.mpf(alias.b)))
    return out
