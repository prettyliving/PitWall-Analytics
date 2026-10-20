"""Matplotlib charts for the race pace and consistency analysis.

Design rules followed (so the charts read as one system):
* one axis per chart, never dual-axis
* magnitude uses a single hue; tyre compounds use their conventional colours
  *plus* a distinct marker shape, so identity is never colour alone
* thin marks, recessive grid, text in neutral ink (not the series colour)
* only the points that matter are labelled directly
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analysis import fmt_lap

INK = "#1f2933"          # primary text
INK_MUTED = "#6b7785"    # secondary text, axes
GRID = "#e3e7ec"
SURFACE = "#ffffff"
MAGNITUDE = "#2f6db5"    # single hue for magnitude charts
HIGHLIGHT = "#d1495b"    # one accent for the point being called out

COMPOUND_STYLE = {
    "SOFT":         {"color": "#d1495b", "marker": "o"},
    "MEDIUM":       {"color": "#e0a100", "marker": "s"},
    "HARD":         {"color": "#6b7785", "marker": "^"},
    "INTERMEDIATE": {"color": "#2e9e5b", "marker": "D"},
    "WET":          {"color": "#2f6db5", "marker": "v"},
}
FALLBACK_STYLE = {"color": "#9aa5b1", "marker": "x"}


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_MUTED,
        "axes.titlecolor": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "text.color": INK,
        "font.size": 10,
        "legend.frameon": False,
        "figure.dpi": 110,
    })


def _style(compound: str | None) -> dict:
    return COMPOUND_STYLE.get((compound or "").upper(), FALLBACK_STYLE)


def plot_pace_distribution(clean: pd.DataFrame, summary: pd.DataFrame):
    """Every clean lap per driver as a strip, with the median marked.
    Drivers are ordered fastest to slowest by median pace."""
    apply_style()
    order = summary["code"].tolist()
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(order) + 1.6))
    rng = np.random.default_rng(0)
    for i, code in enumerate(order):
        laps = clean.loc[clean["code"] == code, "lap_time_s"].to_numpy()
        jitter = rng.uniform(-0.22, 0.22, size=len(laps))
        ax.scatter(laps, np.full(len(laps), i) + jitter, s=9, color=MAGNITUDE,
                   alpha=0.35, linewidths=0)
        ax.plot([np.median(laps)] * 2, [i - 0.34, i + 0.34], color=INK, lw=2)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Clean lap time (s)")
    ax.set_title("Race pace: every clean lap, median marked")
    return fig


def plot_consistency(summary: pd.DataFrame):
    """Detrended lap-time spread per driver (lower = more consistent)."""
    apply_style()
    d = summary.dropna(subset=["consistency_s"]).sort_values("consistency_s")
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(d) + 1.6))
    colors = [HIGHLIGHT if i < 3 else MAGNITUDE for i in range(len(d))]
    ax.barh(d["code"], d["consistency_s"], color=colors, height=0.62)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    for i, v in enumerate(d["consistency_s"]):
        if i < 3 or i == len(d) - 1:   # label the three best and the worst only
            ax.text(v + 0.005, i, f"{v:.2f}s", va="center", color=INK_MUTED, fontsize=9)
    ax.set_xlabel("Lap-time spread after removing tyre/fuel trend (s) - lower is better")
    ax.set_title("Consistency: three most consistent drivers highlighted")
    return fig


def plot_stints(clean: pd.DataFrame, codes: list[str], ncols: int = 2):
    """Lap time vs lap number for chosen drivers (small multiples, shared axes).
    Colour and marker shape both encode the tyre compound."""
    apply_style()
    nrows = int(np.ceil(len(codes) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.4 * ncols, 3.2 * nrows),
                             sharex=True, sharey=True, squeeze=False)
    seen = set()
    for ax, code in zip(axes.flat, codes):
        g = clean[clean["code"] == code]
        for compound, gc in g.groupby("compound"):
            st = _style(compound)
            ax.scatter(gc["lap_number"], gc["lap_time_s"], s=22, marker=st["marker"],
                       color=st["color"], linewidths=0, label=compound)
            seen.add(compound)
        ax.set_title(code, fontsize=11)
    for ax in axes.flat[len(codes):]:
        ax.set_visible(False)
    handles = [plt.Line2D([], [], marker=_style(c)["marker"], color=_style(c)["color"],
                          linestyle="", markersize=7, label=c) for c in sorted(seen)]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.02))
    fig.supxlabel("Lap", y=0.04, color=INK_MUTED)
    fig.supylabel("Lap time (s)", color=INK_MUTED)
    fig.suptitle("Clean laps by stint and tyre compound", x=0.02, ha="left",
                 fontweight="bold", fontsize=13)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    return fig


def plot_pace_vs_consistency(summary: pd.DataFrame):
    """Fast and consistent sits bottom-left. Every driver is labelled (n is small)."""
    apply_style()
    d = summary.dropna(subset=["consistency_s"])
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.scatter(d["gap_to_best_s"], d["consistency_s"], s=48, color=MAGNITUDE, linewidths=0)
    for _, r in d.iterrows():
        ax.annotate(r["code"], (r["gap_to_best_s"], r["consistency_s"]),
                    xytext=(5, 4), textcoords="offset points", fontsize=8.5, color=INK_MUTED)
    ax.set_xlabel("Gap to fastest median pace (s)")
    ax.set_ylabel("Lap-time spread, detrended (s)")
    ax.set_title("Pace vs consistency")
    return fig


def summary_table(summary: pd.DataFrame) -> pd.DataFrame:
    """Display-ready table."""
    t = summary.copy()
    t["median_pace"] = t["median_pace_s"].map(fmt_lap)
    t["gap_to_best_s"] = t["gap_to_best_s"].round(3)
    t["consistency_s"] = t["consistency_s"].round(3)
    t["cv_pct"] = t["cv_pct"].round(2)
    t["avg_slope_s_per_lap"] = t["avg_slope_s_per_lap"].round(3)
    return t[["pace_rank", "code", "team", "clean_laps", "median_pace", "gap_to_best_s",
              "consistency_s", "cv_pct", "avg_slope_s_per_lap"]]
