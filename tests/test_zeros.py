import pytest

from zeta_checker import zeros


def test_first_ordinates():
    g = zeros.ordinates(3)
    ref = [14.134725141734693, 21.022039638771555, 25.010857580145688]
    assert [float(x) for x in g] == pytest.approx(ref, abs=1e-12)


@pytest.mark.parametrize("t, n", [(20, 1), (100, 29), (1000, 649), (10_000, 10_142)])
def test_trudgian_brackets_known_counts(t, n):
    lo, hi = zeros.count_bounds(t)
    assert lo <= n <= hi


def test_smooth_count_tracks_the_zeros():
    g = zeros.ordinates(50)
    assert all(abs(zeros.smooth_count(t) - k) < 2 for k, t in enumerate(g, 1))
