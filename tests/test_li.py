import mpmath
import pytest

from zeta_checker import li, zeros

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


def test_li_matches_maslanka_table():
    lam = li.li_coefficients(15)
    for n, (x, ref) in enumerate(zip(lam, MASLANKA, strict=True), 1):
        printed = 10.0 ** -len(ref.split(".")[1])
        assert x == pytest.approx(float(ref), abs=printed / 2), n


def test_li_closed_forms():
    g, g1 = mpmath.euler, mpmath.stieltjes(1)
    lam1 = 1 + g / 2 - mpmath.log(4 * mpmath.pi) / 2
    lam2 = 1 + g - g**2 + mpmath.pi**2 / 8 - mpmath.log(4 * mpmath.pi) - 2 * g1
    lam = li.li_coefficients(2)
    assert lam[0] == pytest.approx(float(lam1), abs=1e-14)
    assert lam[1] == pytest.approx(float(lam2), abs=1e-14)


def test_li_100_against_maslanka_and_voros():
    lam = li.li_coefficients(100)
    assert lam[-1] == pytest.approx(118.603775377, abs=1e-9)
    assert lam[-1] == pytest.approx(li.voros(100), rel=0.02)
    assert all(x > 0 for x in lam)


def test_li_does_not_depend_on_the_contour():
    a = li.li_coefficients(10, r=0.6, m=256)
    b = li.li_coefficients(10, r=0.9, m=1024)
    assert a == pytest.approx(b, abs=1e-12)


@pytest.mark.parametrize("r, m", [(1.0, 512), (0.0, 512), (0.8, 20)])
def test_li_rejects_bad_contours(r, m):
    with pytest.raises(ValueError):
        li.li_coefficients(10, r=r, m=m)


@pytest.fixture(scope="module")
def gammas():
    return zeros.ordinates(101)


def test_archimedean_closed_form_matches_contour():
    contour = li.keiper(li.log_gamma_factor, 20)
    assert [li.archimedean(n) for n in range(1, 21)] == pytest.approx(contour, abs=1e-12)


def test_finite_part_of_lambda_1_is_euler():
    assert li.li_coefficients(1)[0] - li.archimedean(1) == pytest.approx(li.EULER, abs=1e-14)


def test_zero_sum_brackets_the_contour(gammas):
    lam = li.li_coefficients(20)
    for n in range(1, 21):
        z = li.from_zeros(n, gammas)
        assert z.partial < lam[n - 1] < z.partial + z.upper
        assert z.estimate == pytest.approx(lam[n - 1], abs=5e-9 * n * n)


def test_zero_sum_improves_with_height(gammas):
    lam = li.li_coefficients(10)[-1]
    low, high = li.from_zeros(10, gammas[:51]), li.from_zeros(10, gammas)
    assert abs(high.estimate - lam) < abs(low.estimate - lam)
    assert high.upper < low.upper
    assert high.partial / lam < 0.9


def test_zero_sum_needs_monotone_tail(gammas):
    with pytest.raises(ValueError):
        li.from_zeros(800, gammas)
