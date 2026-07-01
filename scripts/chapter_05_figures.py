"""
Generate the fee-growth figure for Chapter 5: 手续费与协议费.

A constant-product diagram showing why a swap with fee makes the pool jump from
the curve xy = k onto a higher curve xy = k' > k:

  - A  : pre-trade reserves, on xy = k
  - B  : where a *fee-free* trade would land — still on xy = k
  - B' : where the *actual* (fee-charging) trade lands — on xy = k' > k, because
         the trader is sent less Y and the difference is retained as the fee

The vertical gap between B and B' is the fee kept in the pool, and the gap
between the two curves is the growth of k.

Output: zh/src/images/ch05/fee_growth.png (1600 px-wide @ 200 DPI).
Reuses the publication theme of chapter_01/03/04 figures.

NOTE on the fee rate: the real V2 fee is 0.3% (γ = 0.003), which would make the
B–B' gap invisibly small. For pedagogical clarity the figure uses an exaggerated
γ = 0.2; this is stated in the caption.
"""

import os
import warnings

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.patches import FancyArrowPatch
from matplotlib.font_manager import FontProperties

warnings.filterwarnings("ignore", message="Glyph .* missing from font")

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

FP_BOLD = FontProperties(family="Inter", weight="bold")
DPI = 200

C_K = "#3a7ca5"      # steel blue — original curve xy = k
C_K2 = "#dd8452"     # amber — higher curve xy = k'
C_INK = "#1f2933"
C_SUB = "#52606d"
C_FEE = "#4c9a6e"    # green — retained fee
C_A = "#2b6cb0"      # point A
C_GUIDE = "#cbd2d9"  # light guide lines

# Concrete numbers (γ exaggerated to 0.2 so the fee wedge is visible).
X0, Y0 = 4.0, 4.0          # pre-trade reserves A ; k = 16
DX = 2.0                   # input Δx
GAMMA = 0.2                # exaggerated fee rate
K = X0 * Y0                # 16
DY_FREE = DX / (X0 + DX) * Y0          # fee-free output → lands on xy = k
DY_FEE = (1 - GAMMA) * DX / (X0 + (1 - GAMMA) * DX) * Y0   # with-fee output
K2 = (X0 + DX) * (Y0 - DY_FEE)         # post-trade product k' > k

A = (X0, Y0)                       # (4, 4)
B = (X0 + DX, Y0 - DY_FREE)        # fee-free landing, on xy = k
Bp = (X0 + DX, Y0 - DY_FEE)        # actual landing, on xy = k'


def plot_fee_growth():
    fig, ax = plt.subplots(figsize=(8.0, 6.4), layout="constrained")

    xs = [i / 100 for i in range(280, 801)]        # 2.80 .. 8.00
    ax.plot(xs, [K / x for x in xs], color=C_K, lw=2.2, zorder=3,
            label=r"$xy = k$")
    ax.plot(xs, [K2 / x for x in xs], color=C_K2, lw=2.0, ls=(0, (5, 3)),
            zorder=3, label=r"$xy = k' > k$")

    # guide lines from axes to the points
    for (px, py), style in [(A, "-"), (B, "-"), (Bp, (0, (2, 2)))]:
        ax.plot([px, px], [0, py], color=C_GUIDE, lw=1.0, ls=style, zorder=1)
        ax.plot([0, px], [py, py], color=C_GUIDE, lw=1.0, ls=style, zorder=1)

    # fee-free trade path A → B along the curve (subtle)
    arc_x = [i / 100 for i in range(int(X0 * 100), int((X0 + DX) * 100) + 1)]
    ax.plot(arc_x, [K / x for x in arc_x], color=C_K, lw=3.2, alpha=0.35,
            zorder=2, solid_capstyle="round")

    # the retained fee = vertical gap between B and B' (prominent, green)
    ax.add_patch(FancyArrowPatch(
        (B[0], B[1]), (Bp[0], Bp[1]), arrowstyle="<->",
        mutation_scale=14, lw=2.4, color=C_FEE, zorder=6,
    ))

    # the three reserve points
    for (px, py), color in [(A, C_A), (B, C_K), (Bp, C_K2)]:
        ax.scatter([px], [py], s=52, color=color, edgecolor="white",
                   linewidth=1.4, zorder=7)

    # Δx horizontal extent arrow (below the points)
    y_dx = 1.55
    ax.add_patch(FancyArrowPatch(
        (X0, y_dx), (X0 + DX, y_dx), arrowstyle="<->",
        mutation_scale=13, lw=1.8, color=C_SUB, zorder=5,
    ))

    # ── labels ─────────────────────────────────────────────────────────
    def lab(xy, text, dx=0.18, dy=0.18, color=C_INK, bold=False, ha="left"):
        fp = dict(fontproperties=FP_BOLD) if bold else {}
        ax.text(xy[0] + dx, xy[1] + dy, text, fontsize=12.5, color=color,
                ha=ha, va="bottom", zorder=8, **fp)

    lab(A, "A", color=C_A, bold=True)
    lab(B, "B", dx=0.18, dy=-0.42, color=C_K, bold=True)       # below B
    lab(Bp, "B'", dx=0.18, dy=0.12, color=C_K2, bold=True)     # above B'

    # curve labels at the left end of each curve
    ax.text(2.86, K / 2.86 + 0.12, r"$xy = k$", fontsize=12, color=C_K,
            ha="left", va="bottom", zorder=5)
    ax.text(2.86, K2 / 2.86 + 0.62, r"$xy = k' > k$", fontsize=12,
            color=C_K2, ha="left", va="bottom", zorder=5)

    # fee wedge label (to the right of the green double-arrow)
    ax.text(B[0] + 0.22, (B[1] + Bp[1]) / 2, "少转出的 Y\n＝手续费",
            fontsize=10.5, color=C_FEE, ha="left", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none",
                      alpha=0.85))

    # Δx label
    ax.text((X0 + X0 + DX) / 2, y_dx - 0.34, r"$\Delta x$（投入）",
            fontsize=11, color=C_SUB, ha="center", va="top", zorder=8)

    # axes
    ax.set_xlim(2.5, 8.4)
    ax.set_ylim(1.2, 6.6)
    ax.set_xlabel(r"代币 X 储量 $x$", fontsize=12)
    ax.set_ylabel(r"代币 Y 储量 $y$", fontsize=12)
    ax.tick_params(colors=C_SUB, labelsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_SUB)
    ax.legend(loc="upper right", fontsize=10.5, frameon=True, framealpha=0.9,
              edgecolor=C_GUIDE)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "zh", "src",
                           "images", "ch05")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "fee_growth.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"✓ Saved: {out}")
    print(f"  k={K}, k'={K2:.3f}; Δy_free={DY_FREE:.3f}, Δy_fee={DY_FEE:.3f}")


if __name__ == "__main__":
    plot_fee_growth()
    print("\nFigure generated successfully.")
