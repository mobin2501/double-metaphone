"""Static PNG charts embedded in the PDF report.

Colors follow the validated reference palette (blue/orange pass CVD and contrast
checks on white). Charts read from the ``summary`` dict saved as the run summary JSON.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display needed when run from a terminal

import matplotlib.pyplot as plt  # noqa: E402

SERIES_1 = "#2a78d6"   # blue
SERIES_2 = "#eb6834"   # orange
SURFACE = "#ffffff"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

RECALL_FPR_CHART = "artifact 4.png"
CANDIDATES_CHART = "artifact 5.png"

FIG_SIZE = (7.0, 3.2)
DPI = 200


def false_positive_rate(specificity: float | None) -> float | None:
    return None if specificity is None else 1 - specificity


def _nan(value: float | None) -> float:
    return math.nan if value is None else value


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["bottom"].set_linewidth(1)
    ax.grid(axis="y", color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=TEXT_MUTED, labelsize=8, length=0)
    ax.xaxis.label.set_color(TEXT_SECONDARY)
    ax.yaxis.label.set_color(TEXT_SECONDARY)


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return path


def recall_fpr_chart(summary: dict, path: Path) -> Path:
    """Recall and false-positive rate per query length on one 0-100% axis."""
    by_length = summary["by_length"]
    lengths = [int(k) for k in by_length]
    recall = [_nan(s["recall"]) * 100 for s in by_length.values()]
    fpr = [_nan(false_positive_rate(s["specificity"])) * 100 for s in by_length.values()]

    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=SURFACE)
    _style_axes(ax)
    marker = dict(marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.plot(lengths, recall, color=SERIES_1, linewidth=2, label="Recall (positives found)",
            solid_capstyle="round", **marker)
    ax.plot(lengths, fpr, color=SERIES_2, linewidth=2, label="False-positive rate (negatives matched)",
            solid_capstyle="round", **marker)
    ax.set_ylim(-3, 103)
    ax.set_yticks(range(0, 101, 25))
    ax.set_yticklabels([f"{v}%" for v in range(0, 101, 25)])
    ax.set_xticks(lengths)
    ax.set_xlabel("Query length (characters)", fontsize=9)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, frameon=False,
              fontsize=8, labelcolor=TEXT_SECONDARY, handlelength=1.5, borderaxespad=0)
    return _save(fig, path)


def candidates_chart(summary: dict, path: Path) -> Path:
    """Mean number of names returned per query, by query length."""
    by_length = summary["by_length"]
    lengths = [int(k) for k in by_length]
    means = [_nan(s["mean_candidates"]) for s in by_length.values()]

    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=SURFACE)
    _style_axes(ax)
    ax.bar(lengths, means, width=0.6, color=SERIES_1, linewidth=0)
    ax.set_xticks(lengths)
    ax.set_xlabel("Query length (characters)", fontsize=9)
    ax.set_ylabel("Mean names returned", fontsize=9)

    # Label only the extreme bar; the axis and the report table carry the rest.
    finite = [(m, x) for m, x in zip(means, lengths) if not math.isnan(m)]
    if finite:
        peak, peak_x = max(finite)
        ax.annotate(f"{peak:.1f}", (peak_x, peak), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, color=TEXT_PRIMARY)
        ax.set_ylim(0, max(peak * 1.15, 1))
    return _save(fig, path)


def build_charts(summary: dict, charts_dir: Path) -> dict[str, Path]:
    charts_dir.mkdir(parents=True, exist_ok=True)
    return {
        "recall_fpr": recall_fpr_chart(summary, charts_dir / RECALL_FPR_CHART),
        "candidates": candidates_chart(summary, charts_dir / CANDIDATES_CHART),
    }
