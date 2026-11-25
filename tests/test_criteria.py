import mpmath
import pytest

from zeta_checker import criteria

A067698 = [2, 3, 4, 5, 6, 8, 9, 10, 12, 16, 18, 20, 24, 30, 36, 48, 60, 72, 84, 120, 180, 240, 360]
A067698 += [720, 840, 2520, 5040]

MASLANKA = [
    "0.0230957089661",
    "0.0923457352280",
    "0.207638920554",
    "0.368790479492",
    "0.575542714461",
    "0.827566012282",
    "1.12446011757",
    "1.46575567715",
    "1.85091604838",
    "2.27933936319",
    "2.75036083822",
    "3.26325532062",
    "3.81724005785",
    "4.41147767868",
    "5.04507937203",
]


def test_sigma_small():
    assert criteria.sigma_table(12)[1:] == [1, 3, 4, 7, 6, 12, 8, 15, 13, 18, 12, 28]


def test_robin_exceptions_are_oeis_a067698():
    assert criteria.robin_exceptions(100_000) == A067698


def test_lagarias_holds_with_equality_only_at_one():
    lag = criteria.lagarias(20_000)
    assert lag.violations == [] and lag.equal == [1]
    assert 0 < lag.slack < 0.05


def test_li_matches_maslanka_table():
    lam = criteria.li_coefficients(15)
    for n, (x, ref) in enumerate(zip(lam, MASLANKA, strict=True), 1):
        printed = 10.0 ** -len(ref.split(".")[1])
        assert x == pytest.approx(float(ref), abs=printed / 2), n


def test_li_closed_forms():
    g, g1 = mpmath.euler, mpmath.stieltjes(1)
    lam1 = 1 + g / 2 - mpmath.log(4 * mpmath.pi) / 2
    lam2 = 1 + g - g**2 + mpmath.pi**2 / 8 - mpmath.log(4 * mpmath.pi) - 2 * g1
    lam = criteria.li_coefficients(2)
    assert lam[0] == pytest.approx(float(lam1), abs=1e-14)
    assert lam[1] == pytest.approx(float(lam2), abs=1e-14)


def test_li_100_against_maslanka_and_voros():
    lam = criteria.li_coefficients(100)
    assert lam[-1] == pytest.approx(118.603775377, abs=1e-9)
    assert lam[-1] == pytest.approx(criteria.voros(100), rel=0.02)
    assert all(x > 0 for x in lam)


def test_li_does_not_depend_on_the_contour():
    a = criteria.li_coefficients(10, r=0.6, m=256)
    b = criteria.li_coefficients(10, r=0.9, m=1024)
    assert a == pytest.approx(b, abs=1e-12)


@pytest.mark.parametrize("r, m", [(1.0, 512), (0.0, 512), (0.8, 20)])
def test_li_rejects_bad_contours(r, m):
    with pytest.raises(ValueError):
        criteria.li_coefficients(10, r=r, m=m)
