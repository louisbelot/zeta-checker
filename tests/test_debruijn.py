import mpmath
import pytest

from zeta_checker import debruijn, zeros


@pytest.mark.parametrize("z", [10, 25.5, mpmath.mpc(10, 1), mpmath.mpc(40, -3)])
def test_h0_is_xi(z):
    want = debruijn.xi(0.5 + 1j * mpmath.mpmathify(z) / 2) / 8
    assert abs(debruijn.H(0, z) - want) < 1e-14 * abs(want)


def test_heat_equation():
    h = mpmath.mpf("1e-4")
    dt = (debruijn.H(0.1 + h, 30) - debruijn.H(0.1 - h, 30)) / (2 * h)
    assert abs(dt + debruijn.H(0.1, 30, 2)) < 1e-8 * abs(dt)


def test_derivatives_by_differences():
    h = mpmath.mpf("1e-5")
    for d in (1, 2):
        diff = (debruijn.H(0.05, 33 + h, d - 1) - debruijn.H(0.05, 33 - h, d - 1)) / (2 * h)
        assert abs(diff - debruijn.H(0.05, 33, d)) < 1e-8 * abs(diff)


def test_first_zeros_of_h0_are_twice_the_ordinates():
    for g in zeros.ordinates(2):
        assert abs(debruijn.zero(0, 2 * g + 0.05) - 2 * g) < 1e-12


def test_velocity_matches_the_zero_sum():
    xs = [2 * g for g in zeros.ordinates(50)]
    for k in (0, 3):
        v = debruijn.velocity(0, xs[k])
        assert abs(debruijn.velocity_from_zeros(k, xs) - v) < 5e-6 * abs(v)


def test_zero_moves_with_the_predicted_velocity():
    x0 = 2 * zeros.ordinates(1)[0]
    dt = mpmath.mpf("0.01")
    v = debruijn.velocity(0, x0)
    slope = (debruijn.zero(dt, x0) - debruijn.zero(-dt, x0)) / (2 * dt)
    assert abs(slope - v) < 1e-4 * abs(v)
