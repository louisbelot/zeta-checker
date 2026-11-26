import math

import mpmath
import pytest

from zeta_checker import criteria

A067698 = [2, 3, 4, 5, 6, 8, 9, 10, 12, 16, 18, 20, 24, 30, 36, 48, 60, 72, 84, 120, 180, 240, 360]
A067698 += [720, 840, 2520, 5040]


def test_sigma_small():
    assert criteria.sigma_table(12)[1:] == [1, 3, 4, 7, 6, 12, 8, 15, 13, 18, 12, 28]


def test_robin_exceptions_are_oeis_a067698():
    assert criteria.robin_exceptions(100_000) == A067698


def test_lagarias_holds_with_equality_only_at_one():
    lag = criteria.lagarias(20_000)
    assert lag.violations == [] and lag.equal == [1]
    assert 0 < lag.slack < 0.05


def integral(f, h, k, upto):
    parts = [1 / (h * k)]
    for m in range(1, upto):
        a, b = h * (m // h), k * (m // k)

        def F(u, a=a, b=b):
            return u - (a + b) * math.log(u) - a * b / u

        parts.append((F(m + 1) - F(m)) / (h * k))
    period = h * k // math.gcd(h, k)
    mean = sum(mpmath.quad(f, [m, m + 1]) for m in range(period)) / period
    return math.fsum(parts) + float(mean) / upto


@pytest.mark.parametrize("h, k", [(1, 1), (1, 2), (2, 3), (3, 5), (4, 6), (7, 4), (5, 12)])
def test_vasyunin_gram_against_integration(h, k):
    f = lambda u: mpmath.frac(u / h) * mpmath.frac(u / k)  # noqa: E731
    assert float(criteria.gram(h, k)) == pytest.approx(integral(f, h, k, 20_000), abs=1e-6)


def test_gram_diagonal_one():
    assert float(criteria.gram(1, 1)) == pytest.approx(math.log(2 * math.pi) - criteria.EULER)


def test_baez_duarte_first_and_decreasing():
    d = criteria.baez_duarte(30)
    g = criteria.EULER
    assert d[0] == pytest.approx(1 - (1 - g) ** 2 / (math.log(2 * math.pi) - g), abs=1e-12)
    assert all(0 < b <= a for a, b in zip(d, d[1:], strict=False))
    assert d[-1] * math.log(30) == pytest.approx(2 + g - math.log(4 * math.pi), rel=0.1)
