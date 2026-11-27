import math

import mpmath
import numpy as np

from zeta_checker import colossal, criteria

A004490 = [2, 6, 12, 60, 120, 360, 2520, 5040, 55440, 720720, 1441440, 4324320, 21621600]
A004490 += [367567200, 6983776800, 160626866400]


def sigma_over_n(n: int) -> mpmath.mpf:
    out, p = mpmath.mpf(1), 2
    while n > 1:
        a = 0
        while n % p == 0:
            n //= p
            a += 1
        if a:
            out *= mpmath.mpf(p ** (a + 1) - 1) / ((p - 1) * p**a)
        p += 1
    return out


def test_first_terms_are_oeis_a004490():
    assert [n for n, _ in colossal.first(16)] == A004490


def test_segmented_sieve_counts():
    base = colossal.small_primes(1000)
    total = sum(
        len(colossal.primes_between(lo, min(lo + 997, 10**6), base)) for lo in range(0, 10**6, 997)
    )
    assert total == 78498
    assert np.array_equal(colossal.primes_between(0, 10**5, base), colossal.small_primes(10**5 - 1))


def test_critical_exponent_matches_ratio():
    for p, k in [(2, 1), (2, 5), (3, 3), (7, 1), (101, 2), (10007, 1)]:
        with mpmath.workdps(30):
            want = mpmath.log(mpmath.mpf(p ** (k + 1) - 1) / (p ** (k + 1) - p)) / mpmath.log(p)
        assert abs(colossal.critical(p, k) - float(want)) < 1e-14 * float(want)


def test_definition_by_brute_force():
    n = 300_000
    sigma = np.zeros(n + 1)
    for d in range(1, n + 1):
        sigma[d::d] += d
    m = np.arange(2, n + 1)
    ca = colossal.first(10)
    for (N, e), (_, nxt) in zip(ca, ca[1:], strict=False):
        eps = (e + nxt) / 2
        score = np.log(sigma[2:]) - (1 + eps) * np.log(m)
        assert m[np.argmax(score)] == N


def test_small_ca_numbers_are_robin_exceptions():
    exc = set(criteria.robin_exceptions(60_000))
    assert {n for n in A004490 if n <= 5040} <= exc
    assert 55440 not in exc


def test_robin_unconditional_bound():
    for n in A004490[2:]:
        lln = mpmath.log(mpmath.log(n))
        assert sigma_over_n(n) < mpmath.exp(mpmath.euler) * lln + mpmath.mpf("0.6483") / lln


def test_scan_against_exact_arithmetic():
    ca = colossal.first(10**6, limit=2000)
    s = colossal.scan(2000)
    assert s.count == len(ca) - 8
    assert abs(s.log_n - float(mpmath.log(ca[-1][0]))) < 1e-12 * s.log_n
    with mpmath.workdps(40):
        D = [
            (mpmath.exp(mpmath.euler) * mpmath.log(mpmath.log(n)) - sigma_over_n(n))
            * mpmath.sqrt(mpmath.log(n))
            for n, _ in ca[8:]
        ]
    lowest = min(D)
    assert abs(s.lowest[0] - float(lowest)) < 1e-11
    assert abs(s.lowest[1] - math.log(55440)) < 1e-12


def test_scan_holds_with_margin():
    s = colossal.scan(10**7, segment=10**6)
    assert s.count == 664579 + len(colossal.higher_events(10**7)[0]) - 8
    assert s.slack > 0
    assert s.gap > 1e3 * colossal.U
    assert s.error < 1e-10
