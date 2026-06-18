"""
Generate publication-quality figures for Chapter 1: Constant Product Market Maker.

Figure 1: CPMM constant product curve (x · y = k hyperbola)
Figure 2: Impermanent Loss vs price ratio
Figure 3: ETH/USDC order book schematic (asks / bids / spread)

Uses seaborn + matplotlib with paper-context styling for journal-quality output.
Target: 1600 px wide PNG at 200 DPI → 8 inches.
"""

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib import ticker

# ---------------------------------------------------------------------------
# Publication-quality theme
# ---------------------------------------------------------------------------
# context="paper": 0.8× baseline scaling (journal figures)
# style="ticks":   white background, no grid, ticks on bottom/left
# font_scale=1.35: slightly larger than paper default for readability at 200 DPI
sns.set_theme(context="paper", style="ticks", font_scale=1.35)

# Font: Inter (clean geometric sans-serif, available on system)
# Fallback: DejaVu Sans (always bundled with matplotlib)
# Mathtext: dejavusans — consistent with Inter's geometric style
# Note: We do NOT set text.usetex=True because LaTeX rendering is slow and
#       the DejaVu mathtext engine produces clean output for our formulas.
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "DejaVu Sans"],
    "mathtext.fontset": "dejavusans",
    "mathtext.default": "it",
    "text.usetex": False,
    # Axes — thin, professional spines
    "axes.linewidth": 0.8,
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#222222",
    "axes.labelweight": "normal",
    # Ticks — subtle, outward
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 4.5,
    "ytick.major.size": 4.5,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.minor.size": 2.5,
    "ytick.minor.size": 2.5,
    "xtick.minor.width": 0.6,
    "ytick.minor.width": 0.6,
    "xtick.major.pad": 5.0,
    "ytick.major.pad": 5.0,
    # Lines — anti-aliased, crisp
    "lines.linewidth": 2.0,
    "lines.antialiased": True,
    "patch.antialiased": True,
    # Figure / save
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    # Legend
    "legend.framealpha": 0.95,
    "legend.edgecolor": "#cccccc",
    # Grid (used sparingly)
    "grid.linewidth": 0.4,
    "grid.alpha": 0.30,
})

# Target dimensions: 1600 px wide → 8 inches at 200 DPI
FIG_WIDTH_PX = 1600
DPI = 200
FIG_WIDTH_IN = FIG_WIDTH_PX / DPI

# ---------------------------------------------------------------------------
# Color palette — curated for print + screen, colorblind-safe
#   Derived from seaborn "muted" palette with manual adjustments
# ---------------------------------------------------------------------------
C_CURVE    = "#3a7ca5"   # steel blue — main curve / primary data
C_POINT_A  = "#c44e52"   # muted red — point A / reference markers
C_POINT_B  = "#4c9a6e"   # sage green — point B / zero-loss marker
C_ARROWS   = "#6c757d"   # warm gray — annotation arrows
C_ACCENT   = "#dd8452"   # amber — accent highlights
C_GRID     = "#cccccc"   # light gray — subtle grid lines


# =========================================================================
# Figure 1: Constant Product Curve  x · y = k
# =========================================================================
def plot_cpmm_curve():
    k = 100.0
    x = np.linspace(1.5, 55, 600)
    y = k / x

    # Points on the curve: A (before swap) and B (after swap)
    x_a, y_a = 10.0, k / 10.0   # A = (10, 10)
    x_b, y_b = 20.0, k / 20.0   # B = (20, 5)

    fig_height_in = FIG_WIDTH_IN * 0.65
    fig, ax = plt.subplots(
        figsize=(FIG_WIDTH_IN, fig_height_in),
        layout="constrained",
    )

    # ── Main curve ──────────────────────────────────────────────────────
    ax.plot(x, y, color=C_CURVE, linewidth=3.0, zorder=5,
            label=r"$x \cdot y = k$")

    # ── Subtle gradient fill under curve ────────────────────────────────
    ax.fill_between(x, y, alpha=0.07, color=C_CURVE, zorder=1)

    # ── Points A and B ──────────────────────────────────────────────────
    point_style = dict(
        markersize=10, zorder=10,
        markeredgecolor="white", markeredgewidth=2.0,
    )
    annotations = [
        (x_a, y_a, r"$A\;(x_1,\, y_1)$", C_POINT_A, (0, 65)),
        (x_b, y_b, r"$B\;(x_2,\, y_2)$", C_POINT_B, (85, 55)),
    ]
    for px, py, label, color, offset in annotations:
        ax.plot(px, py, "o", color=color, **point_style)
        ax.annotate(
            label, xy=(px, py), xytext=offset,
            textcoords="offset points",
            fontsize=13, fontweight="bold", color=color,
            ha="center", va="center",
            bbox=dict(
                boxstyle="round,pad=0.4",
                fc="white", ec=color, alpha=0.95, lw=1.3,
            ),
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=1.6,
                shrinkA=5, shrinkB=3,
            ),
            zorder=11,
        )

    # ── Dashed projection lines to axes ─────────────────────────────────
    for px, py, color in [(x_a, y_a, C_POINT_A), (x_b, y_b, C_POINT_B)]:
        ax.plot([px, px], [0, py], "--", color=color, alpha=0.30,
                lw=1.2, zorder=3)
        ax.plot([0, px], [py, py], "--", color=color, alpha=0.30,
                lw=1.2, zorder=3)

    # ── Swap arrow from A to B along the curve ──────────────────────────
    ax.annotate(
        "", xy=(x_b, y_b), xytext=(x_a, y_a),
        arrowprops=dict(
            arrowstyle="-|>", color=C_ARROWS, lw=2.2,
            connectionstyle="arc3,rad=-0.3",
            shrinkA=14, shrinkB=14,
        ),
        zorder=8,
    )
    # Swap label — placed at midpoint of arc
    mid_x = (x_a + x_b) / 2
    mid_y = k / mid_x
    ax.text(
        mid_x + 4.0, mid_y + 8.0,
        r"Swap: $\Delta x \rightarrow \Delta y$",
        fontsize=12.5, color=C_ARROWS, fontstyle="italic",
        ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.92),
        zorder=9,
    )

    # ── Axes configuration ──────────────────────────────────────────────
    ax.set_xlim(0, 55)
    ax.set_ylim(0, 68)
    ax.set_xlabel(r"Reserve $x$ (Token X)", fontsize=14, labelpad=10)
    ax.set_ylabel(r"Reserve $y$ (Token Y)", fontsize=14, labelpad=10)
    ax.set_title(
        r"Constant Product Curve  $x \cdot y = k$",
        fontsize=16, fontweight="bold", pad=18,
    )

    # Custom tick marks — only show meaningful values
    ax.set_xticks([0, x_a, x_b, 50])
    ax.set_xticklabels(["0", r"$x_1$", r"$x_2$", ""], fontsize=13)
    ax.set_yticks([0, y_b, y_a, 60])
    ax.set_yticklabels(["0", r"$y_2$", r"$y_1$", ""], fontsize=13)

    # Subtle grid — only major gridlines, behind data
    ax.grid(True, alpha=0.20, linestyle="-", color=C_GRID, which="major")
    ax.set_axisbelow(True)

    # Clean spines: remove top + right (seaborn despine)
    sns.despine(ax=ax, offset=0)

    # Save
    fig.savefig("ch01_cpmm_curve.png", dpi=DPI)
    plt.close(fig)
    print("✓ Saved: ch01_cpmm_curve.png")


# =========================================================================
# Figure 2: Impermanent Loss  IL = 1 − 2√r / (r + 1)
# =========================================================================
def plot_impermanent_loss():
    r = np.linspace(0.05, 5.0, 800)
    il = 1.0 - (2.0 * np.sqrt(r)) / (r + 1.0)

    # Key reference points with (r, label, annotation_offset)
    ref_points = [
        (0.5,  r"$r=0.5$", (  0,  60)),
        (2.0,  r"$r=2$",   ( 70,   0)),
        (3.0,  r"$r=3$",   ( 70,   0)),
        (5.0,  r"$r=5$",   (-70,   0)),
    ]

    fig_height_in = FIG_WIDTH_IN * 0.62
    fig, ax = plt.subplots(
        figsize=(FIG_WIDTH_IN, fig_height_in),
        layout="constrained",
    )

    # ── Main IL curve ───────────────────────────────────────────────────
    ax.plot(
        r, il * 100, color=C_CURVE, linewidth=3.0, zorder=5,
        label="Impermanent Loss",
    )

    # ── Subtle fill under curve ─────────────────────────────────────────
    ax.fill_between(r, il * 100, alpha=0.07, color=C_CURVE, zorder=1)

    # ── Reference lines ─────────────────────────────────────────────────
    ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.5,
               alpha=0.5, zorder=2)
    ax.axvline(x=1.0, color="gray", linestyle="--", linewidth=0.7,
               alpha=0.35, zorder=2)

    # ── Highlighted points (r ≠ 1) ─────────────────────────────────────
    for rv, label, offset in ref_points:
        ilv = (1 - 2 * np.sqrt(rv) / (rv + 1)) * 100
        ax.plot(rv, ilv, "o", color=C_POINT_A, markersize=9, zorder=10,
                markeredgecolor="white", markeredgewidth=1.8)
        ax.annotate(
            f"{label}\n({ilv:.1f}%)",
            xy=(rv, ilv), xytext=offset, textcoords="offset points",
            fontsize=11.5, color=C_POINT_A, fontweight="bold",
            ha="center", va="center",
            bbox=dict(
                boxstyle="round,pad=0.35", fc="white", ec=C_POINT_A,
                alpha=0.95, lw=1.1,
            ),
            arrowprops=dict(
                arrowstyle="-|>", color=C_POINT_A, lw=1.4,
                shrinkA=4, shrinkB=3,
            ),
            zorder=11,
        )

    # ── r = 1 marker (zero IL) ─────────────────────────────────────────
    ax.plot(1.0, 0.0, "D", color=C_POINT_B, markersize=11, zorder=10,
            markeredgecolor="white", markeredgewidth=1.8)
    ax.annotate(
        r"$r=1$" + "\n(0.0%)",
        xy=(1.0, 0.0), xytext=(0, 60), textcoords="offset points",
        fontsize=11.5, color=C_POINT_B, fontweight="bold",
        ha="center", va="center",
        bbox=dict(
            boxstyle="round,pad=0.35", fc="white", ec=C_POINT_B,
            alpha=0.95, lw=1.1,
        ),
        arrowprops=dict(
            arrowstyle="-|>", color=C_POINT_B, lw=1.4,
            shrinkA=4, shrinkB=3,
        ),
        zorder=11,
    )

    # ── Axes configuration ──────────────────────────────────────────────
    ax.set_xlim(0.0, 5.2)
    ax.set_ylim(-1.0, 28)
    ax.set_xlabel(r"Price Ratio  $r = P\, /\, P_0$", fontsize=14, labelpad=10)
    ax.set_ylabel("Impermanent Loss (%)", fontsize=14, labelpad=10)
    ax.set_title(
        "Impermanent Loss vs. Price Ratio",
        fontsize=16, fontweight="bold", pad=18,
    )

    # X-axis ticks — meaningful breakpoints
    ax.set_xticks([0.5, 1.0, 2.0, 3.0, 4.0, 5.0])
    ax.set_xticklabels(["0.5", "1", "2", "3", "4", "5"], fontsize=13)

    # Y-axis percentage formatting
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f%%"))
    ax.tick_params(axis="both", which="major", labelsize=13)

    # Subtle grid
    ax.grid(True, alpha=0.20, linestyle="-", color=C_GRID, which="major")
    ax.set_axisbelow(True)

    # Legend
    ax.legend(
        fontsize=13, loc="upper left",
        frameon=True, framealpha=0.95,
        edgecolor="#cccccc", fancybox=False,
    )

    # Clean spines
    sns.despine(ax=ax, offset=0)

    # Save
    fig.savefig("ch01_impermanent_loss.png", dpi=DPI)
    plt.close(fig)
    print("✓ Saved: ch01_impermanent_loss.png")


# =========================================================================
# Figure 3: ETH/USDC Order Book schematic  (asks / bids / spread)
#   A clean ladder drawn in the book's publication theme, replacing the
#   previous low-res exchange screenshot. Prices match the chapter prose:
#   market-maker bid $2,000.00 / ask $2,000.50  →  spread = $0.50.
# =========================================================================
def plot_orderbook():
    # (price in USDC, size in ETH)
    # Asks: highest price on top, best ask last (adjacent to the spread).
    asks = [
        (2001.00, 1.20),
        (2000.90, 0.85),
        (2000.80, 2.10),
        (2000.70, 0.55),
        (2000.60, 1.45),
        (2000.50, 0.95),   # best ask
    ]
    # Bids: best bid first (adjacent to the spread), descending below.
    bids = [
        (2000.00, 1.80),   # best bid
        (1999.90, 1.10),
        (1999.80, 2.45),
        (1999.70, 0.70),
        (1999.60, 1.30),
        (1999.50, 0.60),
    ]
    n = len(asks)
    max_size = max(s for _, s in asks + bids)

    # Landscape canvas, aspect ratio close to the other two figures (~1.45:1)
    fig_height_in = FIG_WIDTH_IN * 0.70
    fig, ax = plt.subplots(
        figsize=(FIG_WIDTH_IN, fig_height_in), layout="constrained",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(-(n + 1.5), n + 1.5)
    ax.axis("off")

    bar_left = 0.22   # depth bars grow rightward from here
    bar_max_w = 0.55  # …reaching here for the largest order
    bar_h = 0.72      # row band height (leaves a clean gap between rows)

    def draw_level(price, size, y, color):
        ax.barh(
            y, width=size / max_size * bar_max_w, left=bar_left,
            height=bar_h, color=color, alpha=0.30,
            edgecolor="none", zorder=1,
        )
        ax.text(0.04, y, f"{price:,.2f}", ha="left", va="center",
                fontsize=13, color=color, fontweight="bold", zorder=3)
        ax.text(0.96, y, f"{size:.2f}", ha="right", va="center",
                fontsize=13, color=color, zorder=3)

    # ── Ask ladder (top, red) ───────────────────────────────────────────
    for i, (price, size) in enumerate(asks):
        draw_level(price, size, n - i - 0.5, C_POINT_A)

    # ── Bid ladder (bottom, green) ──────────────────────────────────────
    for i, (price, size) in enumerate(bids):
        draw_level(price, size, -(i + 0.5), C_POINT_B)

    # ── Spread between best ask (y = 0.5) and best bid (y = -0.5) ───────
    ax.annotate(
        "", xy=(0.50, -0.5), xytext=(0.50, 0.5),
        arrowprops=dict(arrowstyle="<->", color=C_ARROWS, lw=1.6),
        zorder=4,
    )
    ax.text(
        0.53, 0.0, "Spread = $0.50", ha="left", va="center",
        fontsize=12, color=C_ARROWS, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=C_ARROWS,
                  alpha=0.95, lw=1.0),
        zorder=5,
    )

    # ── Column headers + side banners ───────────────────────────────────
    ax.text(0.04, n + 1.10, "Price (USDC)", ha="left", va="center",
            fontsize=12, color="#555555", fontstyle="italic")
    ax.text(0.96, n + 1.10, "Size (ETH)", ha="right", va="center",
            fontsize=12, color="#555555", fontstyle="italic")
    ax.text(0.04, n + 0.35, "Ask (sell)", ha="left", va="bottom",
            fontsize=12.5, color=C_POINT_A, fontweight="bold")
    ax.text(0.04, -(n + 0.60), "Bid (buy)", ha="left", va="top",
            fontsize=12.5, color=C_POINT_B, fontweight="bold")

    # ── Title ───────────────────────────────────────────────────────────
    ax.set_title("ETH/USDC Order Book", fontsize=16, fontweight="bold", pad=14)

    fig.savefig("ch01_orderbook.png", dpi=DPI)
    plt.close(fig)
    print("✓ Saved: ch01_orderbook.png")


# =========================================================================
if __name__ == "__main__":
    plot_cpmm_curve()
    plot_impermanent_loss()
    plot_orderbook()
    print("\nAll figures generated successfully.")
