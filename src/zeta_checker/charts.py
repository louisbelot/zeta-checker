from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from zeta_checker.criteria import LANDREAU_RICHARD  # noqa: E402


def baez_duarte(d, path: Path) -> None:
    n = np.arange(1, len(d) + 1)
    y = np.asarray(d) * np.log(n)
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.plot(n[1:], y[1:], lw=1, color="#1f5fa8")
    ax.axhline(LANDREAU_RICHARD, color="#c0392b", lw=1, ls="--")
    ax.annotate(
        rf"$2 + \gamma - \log 4\pi = {LANDREAU_RICHARD:.5f}$",
        (5, LANDREAU_RICHARD),
        xytext=(6, -16),
        textcoords="offset points",
        ha="left",
        color="#c0392b",
    )
    ax.set_xscale("log")
    ax.set_xlim(5, len(d))
    ax.set_ylim(0.04, 0.058)
    ax.set_xlabel("N")
    ax.set_ylabel(r"$d_N^2 \log N$")
    ax.set_title(f"Nyman-Beurling-Baez-Duarte distance, N up to {len(d)}")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def colossal(scan, path: Path) -> None:
    from zeta_checker.colossal import RAMANUJAN

    x, y = np.array(scan.curve).T
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.plot(x, y, lw=1.2, color="#1f5fa8")
    ax.axhline(RAMANUJAN, color="#c0392b", lw=1, ls="--")
    ax.annotate(
        rf"$e^\gamma(2\sqrt{{2}} - 4 - \gamma + \log 4\pi) = {RAMANUJAN:.4f}$",
        (x[-1], RAMANUJAN),
        xytext=(-6, -16),
        textcoords="offset points",
        ha="right",
        color="#c0392b",
    )
    ax.set_xscale("log")
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel(r"$\log N$")
    ax.set_ylabel(r"$(e^\gamma \log\log N - \sigma(N)/N)\,\sqrt{\log N}$")
    ax.set_title(f"Robin's inequality on {scan.count:,} colossally abundant numbers")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
