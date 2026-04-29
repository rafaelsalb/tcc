from collections import defaultdict

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sqlalchemy import text

from ..db import engine


def plot_article_date_distribution():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT date_published FROM dates WHERE date_published IS NOT NULL"))
        # `date_published` is stored as text in `dates`; convert to datetime
        dates = pd.to_datetime([row[0] for row in result], errors='coerce').dropna().tolist()

    weekly_counts = defaultdict(lambda: defaultdict(int))
    for date in dates:
        iso_year, week, _ = date.isocalendar()
        weekly_counts[iso_year][week] += 1

    figures = {"by_year": {}, "all_weeks": None}

    for year in sorted(weekly_counts):
        weeks = list(range(1, 54))
        counts = [weekly_counts[year][week] for week in weeks]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(weeks, counts)
        ax.set_xlabel('Week of the Year')
        ax.set_ylabel('Number of Articles')
        ax.set_title(f'Articles per Week in {year}')
        ax.set_xticks(weeks)
        fig.tight_layout()
        figures["by_year"][year] = fig

    # Build a 2D matrix: rows -> years, cols -> ISO weeks (1..53)
    years = sorted(weekly_counts)
    weeks = list(range(1, 54))
    data = np.zeros((len(years), len(weeks)), dtype=int)
    for i, year in enumerate(years):
        for j, week in enumerate(weeks):
            data[i, j] = weekly_counts[year][week]

    fig_height = max(3, 0.5 * len(years) + 1)
    fig_width = max(14, 0.25 * len(weeks) + 8)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    # Use pcolormesh so we can draw thin white borders between cells.
    # Transform the article counts with log10(count + 1) for plotting,
    # but keep the color mapping linear in that transformed space.
    X = np.arange(len(weeks) + 1)
    Y = np.arange(len(years) + 1)

    data_raw = data.astype(float)
    # Prepare colorbar ticks based on raw counts (min, quartiles, max)
    flat = data_raw.flatten()
    if flat.size:
        vmin = int(flat.min())
        vmax = int(flat.max())
        q25, q50, q75 = np.percentile(flat, [25, 50, 75]).astype(int)
    else:
        vmin = vmax = q25 = q50 = q75 = 0

    # Transform for plotting: log10(count + 1) so zeros map to 0
    data_plot = np.log10(data_raw + 1)
    pcm = ax.pcolormesh(X, Y, data_plot, cmap='viridis', edgecolors='white', linewidth=0.35)

    ax.set_xlabel('ISO Week')
    ax.set_ylabel('Year')
    ax.set_title('Articles per Week Across All Years (heatmap)')

    # X ticks: show a reasonable number to avoid clutter, centered on cells
    max_xticks = 20
    step = max(1, len(weeks) // max_xticks)
    xtick_positions = np.arange(0.5, len(weeks), step)
    ax.set_xticks(xtick_positions)
    ax.set_xticklabels([str(w) for w in weeks[::step]], rotation=90)

    # Y ticks: centered on rows
    ytick_positions = np.arange(0.5, len(years))
    ax.set_yticks(ytick_positions)
    ax.set_yticklabels([str(y) for y in years])

    cbar = fig.colorbar(pcm, ax=ax)
    cbar.set_label('Number of Articles (log10 count)')
    # Show min, quartiles, and max on the colorbar but label them with raw counts.
    ticks_raw = [vmin, q25, q50, q75, vmax]
    # Deduplicate and keep order
    seen = set()
    ticks_raw = [x for x in ticks_raw if not (x in seen or seen.add(x))]
    ticks_positions = [np.log10(x + 1) for x in ticks_raw]
    cbar.set_ticks(ticks_positions)
    cbar.set_ticklabels([str(int(x)) for x in ticks_raw])

    fig.tight_layout()
    figures["all_weeks"] = fig

    return figures
