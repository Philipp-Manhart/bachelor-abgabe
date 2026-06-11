from __future__ import annotations

import matplotlib as mpl
import seaborn as sns
from cycler import cycler
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

CM = 1 / 2.54

# Typst: A4 width 21cm - 2 * 3cm margin = 15cm text width.
TEXT_WIDTH_CM = 15.0

# Typst template: set image(width: 90%).
FIG_WIDTH_CM = 0.90 * TEXT_WIDTH_CM

SYSTEM_COLORS = {
    "A": "#4e4e4e",
    "B": "#378d94",
    "C": "#6a408d",
}
COLORS_ACCENT = ["#9671bd", "#7e7e7e", "#77b5b6"]
COLORS_SECONDARY = ["#6a408d", "#4e4e4e", "#378d94"]
COLOR_NEUTRAL = "#8a8a8a"


def set_paper_style() -> None:
    sns.set_theme(
        context="paper",
        style="whitegrid",
        palette=COLORS_ACCENT,
        rc={
            "font.family": "serif",
            "font.serif": [
                "Linux Libertine",
                "Linux Libertine O",
                "Libertinus Serif",
                "Times New Roman",
                "Noto Serif",
                "DejaVu Serif",
            ],
            "font.size": 12,
            "axes.labelsize": 12,
            "axes.titlesize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "legend.title_fontsize": 10,
            "svg.fonttype": "none",
            "axes.edgecolor": COLOR_NEUTRAL,
            "axes.labelcolor": "black",
            "xtick.color": "black",
            "ytick.color": "black",
            "grid.color": "#d9d9d9",
            "grid.linewidth": 0.6,
            "axes.linewidth": 0.8,
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
        },
    )
    mpl.rcParams["axes.prop_cycle"] = cycler(color=COLORS_ACCENT)


def typst_figsize(width_cm: float = FIG_WIDTH_CM, ratio: float = 0.62) -> tuple[float, float]:
    width_in = width_cm * CM
    height_in = width_in * ratio
    return width_in, height_in


def add_minor_y_grid(axis: mpl.axes.Axes, *, percent: bool = False) -> None:
    if percent:
        axis.yaxis.set_minor_locator(MultipleLocator(0.1))
    else:
        axis.yaxis.set_minor_locator(AutoMinorLocator(2))
    axis.grid(True, axis="y", which="minor", color="#ececec", linewidth=0.4)
