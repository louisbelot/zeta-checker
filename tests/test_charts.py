import pytest

from zeta_checker import criteria

charts = pytest.importorskip("zeta_checker.charts")


def test_baez_duarte_chart(tmp_path):
    out = tmp_path / "d.png"
    charts.baez_duarte(criteria.baez_duarte_float(50), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
