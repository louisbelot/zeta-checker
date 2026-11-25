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
