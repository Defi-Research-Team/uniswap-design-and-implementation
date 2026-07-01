"""
Generate the TWAP figure for Chapter 6: Oracles.

Two stacked panels over a block axis:
  - Top:    spot price with a single-block manipulation spike.
  - Bottom: the same spot price (faint) overlaid with a 40-block-window TWAP
            that stays nearly flat — visualising how a one-block spike is
            diluted away by the time-weighted average.

Output: zh/src/images/ch06/twap.png (1600 px-wide @ 200 DPI).

Reuses the publication theme of chapter_01/chapter_03 figures. Latin glyphs use
Inter; Chinese glyphs fall back to WenQuanYi Zen Hei via per-glyph fallback.
"""

import os
import warnings

import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np

warnings.filterwarnings("ignore", message="Glyph .* missing from font")

# ---------------------------------------------------------------------------
# Publication theme (mirrors chapter_01 / chapter_03 figures)
# ---------------------------------------------------------------------------
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["WenQuanYi Zen Hei", "Inter", "DejaVu Sans"],
    "mathtext.fontset": "dejavusans",
    "axes.linewidth": 0.8,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.2,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.unicode_minus": False,
})

# Palette (consistent with ch01 / ch03)
C_SPOT = "#dd8452"   # amber — spot price (manipulable)
C_TWAP = "#4c9a6e"   # sage green — TWAP (resistant)
C_INK = "#1f2933"    # near-black — text
C_SUB = "#52606d"    # gray — secondary text
C_TRUE = "#3a7ca5"   # steel blue — true price reference

DPI = 200


def simulate():
    """Deterministic spot price with one manipulation spike, plus cumulative & TWAP."""
    N = 121                     # blocks
    dt = 12                     # seconds per block
    i = np.arange(N)
    base = 100.0 + 3.0 * np.sin(i / 8.0)   # gentle natural variation around 100
    base[60] = 165.0            # a single block of manipulation, then arbitrage reverts it
    price = base
    cumulative = np.cumsum(price) * dt
    # TWAP over a trailing window of W blocks
    W = 40
    twap = np.full(N, np.nan)
    for k in range(W, N):
        twap[k] = (cumulative[k] - cumulative[k - W]) / (W * dt)
    return i, price, twap


def plot_twap():
    i, price, twap = simulate()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 7.2), layout="constrained",
                                   sharex=True)

    # ── Top: spot price with manipulation spike ─────────────────────────
    ax1.plot(i, price, color=C_SPOT, lw=2.0, label="现货价格 spot")
    ax1.axhline(100, color=C_TRUE, lw=1.0, ls="--", alpha=0.6, label="真实价值")
    ax1.scatter([60], [price[60]], color=C_SPOT, zorder=5, s=45)
    ax1.annotate("单区块操纵尖峰\n（闪电贷拉抬）", xy=(60, price[60]),
                 xytext=(72, 150), fontsize=9.5, color=C_INK,
                 arrowprops=dict(arrowstyle="->", color=C_SUB, lw=1.0))
    ax1.set_ylabel("现货价格", fontsize=11, color=C_INK)
    ax1.set_title("现货价格可被一笔交易瞬时操纵", fontsize=12.5,
                  color=C_INK, fontweight="bold", loc="left", pad=8)
    ax1.set_ylim(85, 175)
    ax1.legend(loc="lower right", fontsize=9, framealpha=0.9)
    ax1.grid(True, alpha=0.25)

    # ── Bottom: TWAP over a 40-block window stays flat ──────────────────
    ax2.plot(i, price, color=C_SPOT, lw=1.2, alpha=0.30, label="现货价格 spot（参照）")
    ax2.plot(i, twap, color=C_TWAP, lw=2.6, label="40 区块窗口 TWAP")
    ax2.axhline(100, color=C_TRUE, lw=1.0, ls="--", alpha=0.6)
    ax2.set_xlabel("区块", fontsize=11, color=C_INK)
    ax2.set_ylabel("均价", fontsize=11, color=C_INK)
    ax2.set_title("长窗口 TWAP 把操纵尖峰稀释殆尽", fontsize=12.5,
                  color=C_INK, fontweight="bold", loc="left", pad=8)
    ax2.set_ylim(85, 175)
    ax2.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax2.grid(True, alpha=0.25)

    # Annotate the tiny TWAP bump caused by the spike
    bump_block = 60 + 40
    ax2.annotate("TWAP 仅微动\n（尖峰占窗口 1/40）",
                 xy=(bump_block, twap[bump_block]),
                 xytext=(bump_block - 8, 132), fontsize=9.5, color=C_TWAP,
                 arrowprops=dict(arrowstyle="->", color=C_TWAP, lw=1.0))

    out_dir = os.path.join(os.path.dirname(__file__), "..", "zh", "src", "images", "ch06")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "twap.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"✓ Saved: {out}")


if __name__ == "__main__":
    plot_twap()
    print("\nFigure generated successfully.")
