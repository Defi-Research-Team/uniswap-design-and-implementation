"""
Generate the architecture figure for Chapter 3: Uniswap V2 two-layer architecture.

Renders the core/periphery split as a layered box-and-arrow diagram with typed
edges (call / create / inherit) and a legend. Output: 1600 px-wide PNG at 200 DPI.

Reuses the publication theme of chapter_01_figures.py. Latin glyphs use Inter;
Chinese glyphs fall back to WenQuanYi Zen Hei (the system's sans-serif CJK font)
via matplotlib's per-glyph font fallback.
"""

import warnings

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.font_manager import FontProperties

# Silence the per-glyph "missing from font(s) Inter" notices — every text element
# below sets a primary font that already contains its glyphs (Inter for Latin
# identifiers, WenQuanYi Zen Hei for everything else), so no fallback is needed.
warnings.filterwarnings("ignore", message="Glyph .* missing from font")

# ---------------------------------------------------------------------------
# Publication theme (mirrors chapter_01_figures.py)
# ---------------------------------------------------------------------------
mpl.rcParams.update({
    "font.family": "sans-serif",
    # WenQuanYi Zen Hei is primary so CJK glyphs render cleanly from it; the bold
    # Latin contract names override this via FP_NAME (Inter) below.
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

# Inter for the prominent Latin contract identifiers (matches ch01 / book font).
FP_NAME = FontProperties(family="Inter", weight="bold")

FIG_W_IN = 8.0      # 1600 px @ 200 DPI
FIG_H_IN = 7.5
DPI = 200

# Coordinate ranges chosen so x:y ≈ figure aspect → negligible box distortion.
X_MAX = 100.0
Y_MAX = 95.0

# Palette (consistent with ch01)
C_PERIPH_BG  = "#fff6ec"   # light amber — periphery layer fill
C_PERIPH_BAR = "#dd8452"   # amber accent — periphery border / titles
C_CORE_BG    = "#eef4fa"   # light blue — core layer fill
C_CORE_BAR   = "#3a7ca5"   # steel blue — core border / titles
C_INK        = "#1f2933"   # near-black — box titles
C_SUB        = "#52606d"   # gray — descriptive text
C_CALL       = "#6c757d"   # warm gray — 调用
C_CREATE     = "#3a7ca5"   # steel blue — 创建
C_INHERIT    = "#4c9a6e"   # sage green — 继承

_ARROW_STYLE = {
    "call":    dict(color=C_CALL,    linestyle="-",  lw=2.0),
    "create":  dict(color=C_CREATE,  linestyle="-",  lw=2.2),
    "inherit": dict(color=C_INHERIT, linestyle="--", lw=2.0),
}


def draw_layer(ax, x, y, w, h, title, bg, bar):
    """A tinted rounded container with a bold layer title in the top-left."""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=2.2",
        linewidth=1.4, edgecolor=bar, facecolor=bg, zorder=1,
    ))
    ax.text(x + 2.5, y + h - 3.0, title, fontsize=12.5, fontweight="bold",
            color=bar, ha="left", va="top", zorder=4)


def draw_contract(ax, cx, cy, w, h, name, lines, accent):
    """A white contract box centered at (cx, cy): bold name + description lines."""
    x0, y0 = cx - w / 2, cy - h / 2
    ax.add_patch(FancyBboxPatch(
        (x0, y0), w, h,
        boxstyle="round,pad=0.02,rounding_size=1.6",
        linewidth=1.6, edgecolor=accent, facecolor="white", zorder=3,
    ))
    ax.text(cx, cy + h / 2 - 2.2, name, fontsize=11.5, fontproperties=FP_NAME,
            color=C_INK, ha="center", va="top", zorder=5)
    ax.text(cx, cy - 0.5, "\n".join(lines), fontsize=9.6, color=C_SUB,
            ha="center", va="center", linespacing=1.45, zorder=5)


def draw_arrow(ax, p0, p1, kind, label=None, label_offset=(0, 0)):
    style = _ARROW_STYLE[kind]
    ax.add_patch(FancyArrowPatch(
        posA=p0, posB=p1, arrowstyle="-|>", mutation_scale=16,
        shrinkA=2, shrinkB=2, zorder=6, **style,
    ))
    if label:
        mx = (p0[0] + p1[0]) / 2 + label_offset[0]
        my = (p0[1] + p1[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, fontsize=9.5, fontweight="bold",
                color=style["color"], ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.9),
                zorder=7)


def plot_architecture():
    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN), layout="constrained")
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(0, Y_MAX)
    ax.axis("off")

    # ── Layer containers ───────────────────────────────────────────────
    draw_layer(ax, 1.5, 51, 97, 42, "外围层 · Periphery (v2-periphery)",
               C_PERIPH_BG, C_PERIPH_BAR)
    draw_layer(ax, 1.5, 6, 97, 42, "核心层 · Core (v2-core)",
               C_CORE_BG, C_CORE_BAR)

    # ── Periphery contracts ────────────────────────────────────────────
    draw_contract(ax, 30, 82, 42, 13, "UniswapV2Router02  (Router01)",
                  ["用户入口 · 滑点保护 · deadline 检查", "多跳路由 · ETH 包装"],
                  C_PERIPH_BAR)
    draw_contract(ax, 80, 84, 26, 9, "UniswapV2Migrator",
                  ["V1 → V2 迁移"], C_PERIPH_BAR)
    draw_contract(ax, 50, 63, 86, 11,
                  "UniswapV2Library · OracleLibrary · LiquidityMathLibrary",
                  ["地址推导 · 量价估算 · 预言机辅助"], C_PERIPH_BAR)

    # ── Core contracts ─────────────────────────────────────────────────
    draw_contract(ax, 15, 31, 22, 13, "UniswapV2Factory",
                  ["注册中心", "协议费治理"], C_CORE_BAR)
    draw_contract(ax, 49, 31, 30, 14, "UniswapV2Pair  (× N)",
                  ["资金池 + LP Token · 兑换（闪电兑换）", "流动性管理 · 价格累加（预言机）"],
                  C_CORE_BAR)
    draw_contract(ax, 83, 31, 24, 13, "UniswapV2ERC20",
                  ["LP Token 基类"], C_CORE_BAR)
    # Core libraries / interfaces footnote
    ax.text(50, 13,
            "库：SafeMath · Math · UQ112x112\n"
            "接口：IUniswapV2Factory / Pair / ERC20 · IERC20 · IUniswapV2Callee",
            fontsize=9.3, color=C_SUB, ha="center", va="center", linespacing=1.7,
            zorder=3)

    # ── Typed arrows ───────────────────────────────────────────────────
    # Periphery (via libraries) → Pair : 调用 (cross-layer)
    draw_arrow(ax, (49, 57.5), (49, 38), "call", label="调用", label_offset=(4.5, 0))
    # Factory → Pair : 创建
    draw_arrow(ax, (26, 31), (34, 31), "create", label="创建", label_offset=(0, 2.4))
    # Pair → ERC20 : 继承
    draw_arrow(ax, (64, 31), (71, 31), "inherit", label="继承", label_offset=(0, 2.4))

    # ── Legend ─────────────────────────────────────────────────────────
    ly = 2.5
    for i, (kind, lab) in enumerate([("call", "调用"), ("create", "创建"), ("inherit", "继承")]):
        x0 = 24 + i * 20
        draw_arrow(ax, (x0, ly), (x0 + 6, ly), kind)
        ax.text(x0 + 7.5, ly, lab, fontsize=9.5, color=C_SUB, ha="left", va="center")

    fig.savefig("architecture.png", dpi=DPI)
    plt.close(fig)
    print("✓ Saved: architecture.png")


if __name__ == "__main__":
    plot_architecture()
    print("\nFigure generated successfully.")
