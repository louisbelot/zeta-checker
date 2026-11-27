from __future__ import annotations

import mpmath

from zeta_checker import zeros


def _dps(x) -> int:
    return 20 + int(mpmath.pi * abs(mpmath.re(x)) / 8 / mpmath.log(10))


def phi(u):
    terms = int(mpmath.sqrt((mpmath.mp.dps + 10) * mpmath.log(10) / mpmath.pi)) + 2
    e4 = mpmath.exp(4 * u)
    return mpmath.fsum(
        (2 * mpmath.pi**2 * n**4 * mpmath.exp(9 * u) - 3 * mpmath.pi * n**2 * mpmath.exp(5 * u))
        * mpmath.exp(-mpmath.pi * n**2 * e4)
        for n in range(1, terms)
    )


def H(t, z, d: int = 0):
    kernel = [
        lambda u: mpmath.cos(z * u),
        lambda u: -u * mpmath.sin(z * u),
        lambda u: -u * u * mpmath.cos(z * u),
    ][d]
    with mpmath.workdps(_dps(z)):
        top = mpmath.log((mpmath.mp.dps + 10) * mpmath.log(10) / mpmath.pi) / 4
        nodes = mpmath.linspace(0, top, max(4, int(abs(z) * top / mpmath.pi)) + 1)
        return +mpmath.quad(lambda u: mpmath.exp(t * u * u) * phi(u) * kernel(u), nodes)


def xi(s):
    return s * (s - 1) / 2 * mpmath.pi ** (-s / 2) * mpmath.gamma(s / 2) * mpmath.zeta(s)


def zero(t, guess, tol=1e-15):
    x = mpmath.mpf(guess)
    for _ in range(30):
        step = H(t, x) / H(t, x, 1)
        x -= step
        if abs(step) < tol * abs(x):
            return x
    raise ArithmeticError(f"Newton did not settle near {guess} at t = {t}")


def velocity(t, x):
    return H(t, x, 2) / H(t, x, 1)


def track(ts, k: int) -> list[list]:
    here = [2 * g for g in zeros.ordinates(k)]
    out, last = [], 0
    for t in ts:
        here = [zero(t, x + velocity(last, x) * (t - last)) for x in here]
        out.append(here)
        last = t
    return out


def velocity_from_zeros(k: int, xs) -> mpmath.mpf:
    x, A = xs[k], xs[-1]
    f = lambda a: 2 * x / (x * x - a * a)  # noqa: E731
    near = mpmath.fsum(f(a) for j, a in enumerate(xs) if j != k)
    smooth = mpmath.quad(
        lambda a: f(a) * mpmath.log(a / (4 * mpmath.pi)) / (4 * mpmath.pi), [A, mpmath.inf]
    )
    tail = smooth - f(A) * (len(xs) - zeros.smooth_count(A / 2))
    return 2 * (1 / (2 * x) + near + tail)
