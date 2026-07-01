"""
Generate the flash-swap sequence figure for Chapter 4: V2 Pool.

A two-lifeline sequence diagram showing the ordering inside `swap` when a
callback is supplied: the Pair optimistically transfers the output, invokes
`uniswapV2Call`, the callee repays, and only then does the K-invariant check
run (reverting the whole call if repayment is insufficient).

Output: zh/src/images/ch04/flash_swap.png (1600 px-wide @ 200 DPI).

Reuses the publication theme of chapter_01/chapter_03 figures.
"""

import os
import warnings

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
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

FP_CODE = FontProperties(family="Inter", weight="bold")
DPI = 200

C_PAIR = "#3a7ca5"   # steel blue — Pair lifeline
C_CALL = "#dd8452"   # amber — callee lifeline
C_INK = "#1f2933"
C_SUB = "#52606d"
C_ARROW = "#34495e"
C_CHECK = "#4c9a6e"  # green — K check
C_REVERT = "#a3533a" # muted red — revert note

X_MAX = 100.0
Y_MAX = 100.0
X_PAIR = 30.0
X_CALL = 72.0


def _header(ax, cx, title, sub, accent, code_title=True):
    ax.add_patch(FancyBboxPatch(
        (cx - 17, 86), 34, 10,
        boxstyle="round,pad=0.02,rounding_size=1.6",
        linewidth=1.6, edgecolor=accent, facecolor="white", zorder=4,
    ))
    # code_title=True → Inter for Latin contract names; False → default sans-serif
    # (its per-glyph fallback chain) for CJK titles. Do NOT pass an explicit CJK
    # FontProperties: that disables fallback and produces tofu.
    title_kw = dict(fontproperties=FP_CODE) if code_title else {}
    ax.text(cx, 92.5, title, fontsize=11.5, color=C_INK,
            ha="center", va="center", zorder=5, **title_kw)
    ax.text(cx, 89.0, sub, fontsize=9.2, color=C_SUB,
            ha="center", va="center", zorder=5)


def _lifeline(ax, x):
    ax.plot([x, x], [86, 16], color=C_SUB, lw=1.2, ls=(0, (4, 3)), zorder=2)


def _msg(ax, y, label, rightward, color=C_ARROW):
    x_from = X_PAIR if rightward else X_CALL
    x_to = X_CALL if rightward else X_PAIR
    ax.add_patch(FancyArrowPatch(
        (x_from, y), (x_to, y), arrowstyle="-|>", mutation_scale=16,
        shrinkA=1, shrinkB=1, lw=2.0, color=color, zorder=6,
    ))
    ax.text((x_from + x_to) / 2, y + 1.8, label, fontsize=9.6, color=C_INK,
            ha="center", va="bottom", zorder=7,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.9))


def _self_msg(ax, y, label, color=C_CHECK):
    # small right-then-down-then-left loop attached to the Pair lifeline
    ax.add_patch(FancyArrowPatch(
        (X_PAIR, y), (X_PAIR - 9, y), connectionstyle="arc3,rad=-1.4",
        arrowstyle="-|>", mutation_scale=14, lw=2.0, color=color, zorder=6,
    ))
    ax.text(X_PAIR + 4, y + 1.8, label, fontsize=9.6, color=color,
            ha="center", va="bottom", zorder=7,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.9))


def plot_flash_swap():
    fig, ax = plt.subplots(figsize=(8.0, 6.8), layout="constrained")
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(0, Y_MAX)
    ax.axis("off")

    # ── Lifelines + headers ─────────────────────────────────────────────
    _lifeline(ax, X_PAIR)
    _lifeline(ax, X_CALL)
    _header(ax, X_PAIR, "UniswapV2Pair", "资金池", C_PAIR)
    _header(ax, X_CALL, "调用者", "实现 IUniswapV2Callee", C_CALL, code_title=False)

    # ── Messages (time flows downward) ──────────────────────────────────
    _msg(ax, 76, "① _safeTransfer(amountOut)\n乐观转出输出代币", rightward=True)
    _msg(ax, 60, "② uniswapV2Call(...)\n回调：调用者自由使用代币", rightward=True)
    _msg(ax, 44, "③ transfer(amountIn)\n归还输入代币（还款）", rightward=False)
    _self_msg(ax, 28, "④ K 不变量检查\n扣 0.3% 后乘积不得下降")

    # ── Revert note ─────────────────────────────────────────────────────
    ax.add_patch(FancyBboxPatch(
        (15, 6), 70, 8,
        boxstyle="round,pad=0.02,rounding_size=1.4",
        linewidth=1.2, edgecolor=C_REVERT, facecolor="#fbf1ef", zorder=3,
    ))
    ax.text(50, 10, "若 ④ 不通过 → 整笔交易回滚，Pair 状态原样不变",
            fontsize=9.8, color=C_REVERT, ha="center", va="center", zorder=5)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "zh", "src", "images", "ch04")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "flash_swap.png")
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"✓ Saved: {out}")


if __name__ == "__main__":
    plot_flash_swap()
    print("\nFigure generated successfully.")
