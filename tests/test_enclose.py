import mpmath
import pytest
from mpmath import iv

from zeta_checker import enclose, li


def contains(box, z):
    return box.real.a <= z.real <= box.real.b and box.imag.a <= z.imag <= box.imag.b


@pytest.fixture
def precise():
    iv.dps, old = 30, iv.dps
    with mpmath.workdps(50):
        yield
    iv.dps = old


@pytest.mark.parametrize("s", ["0.6+1.7j", "2", "5-2j", "0.55-0.3j", "3+10j"])
def test_zeta_and_gamma_enclose_mpmath(precise, s):
    z = mpmath.mpc(s)
    box = iv.mpc(iv.mpf(str(z.real)), iv.mpf(str(z.imag)))
    zeta, gamma = enclose.zeta(box), enclose.gamma(box)
    assert contains(zeta, mpmath.zeta(z)) and contains(gamma, mpmath.gamma(z))
    assert zeta.real.delta < 1e-24 and gamma.real.delta < 1e-24


def test_inverse_square_ordinates_bound():
    bound = enclose.sum_inverse_square_ordinates()
    assert 0.0231049931 < bound.a and bound.b < 0.05


def test_li_enclosures_are_tight_and_positive():
    out = enclose.li_enclosures(30)
    with mpmath.workdps(40):
        lam1 = 1 + mpmath.euler / 2 - mpmath.log(4 * mpmath.pi) / 2
        assert out[0].lo <= lam1 <= out[0].hi
    assert out[9].lo < mpmath.mpf("2.27933936319") + 5e-12 and out[9].hi > 2.27933936319 - 5e-12
    assert all(e.lo > 0 and e.width < 1e-20 and e.aliasing < 1e-29 for e in out)
    lam = li.li_coefficients(30)
    assert all(e.lo - 1e-14 < x < e.hi + 1e-14 for e, x in zip(out, lam, strict=True))


def test_li_100_enclosure_holds_maslanka():
    e = enclose.li_enclosures(100, m=1024, dps=40)[-1]
    assert e.lo < 118.603775377 + 5e-10 and e.hi > 118.603775377 - 5e-10
    assert e.width < 1e-14


@pytest.mark.parametrize("kw", [{"r": "0.95"}, {"m": 40}])
def test_li_enclosures_reject_bad_contours(kw):
    with pytest.raises(ValueError):
        enclose.li_enclosures(30, **kw)


def test_decimals_round_outward():
    e = enclose.Enclosure(1, mpmath.mpf(1) / 3, mpmath.mpf(2) / 3, mpmath.mpf(0))
    assert e.decimals(4) == ("0.3333", "0.6667")
    neg = enclose.Enclosure(1, -mpmath.mpf(2) / 3, -mpmath.mpf(1) / 3, mpmath.mpf(0))
    assert neg.decimals(2) == ("-0.67", "-0.33")
