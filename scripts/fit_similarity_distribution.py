"""Fit simple distributions to MCES similarities from completed chunks.

Usage:
    uv run python scripts/fit_similarity_distribution.py [SAMPLE_NAME]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
from scipy.stats import beta, weibull_min


def load_similarities(result_dir: Path) -> np.ndarray:
    """Load all valid similarities from chunk parquet files."""
    chunk_files = sorted(result_dir.glob("chunk_*.parquet"))
    print(f"Reading {len(chunk_files)} chunk files...")

    similarities: list[float] = []
    for chunk_file in chunk_files:
        table = pq.read_table(chunk_file, columns=["similarity"])
        similarities.extend(table.column("similarity").to_pylist())

    values = np.asarray(similarities, dtype=np.float64)
    return values[~np.isnan(values)]


def main() -> None:
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "massspecgym"
    result_dir = Path(f"data/results/cluster/{sample_name}")
    similarities = load_similarities(result_dir)

    if len(similarities) == 0:
        raise ValueError("No valid similarities found.")

    eps = np.finfo(np.float64).eps
    similarities_beta = np.clip(similarities, eps, 1.0 - eps)
    similarities_positive = np.clip(similarities, eps, None)

    alpha, beta_param, _, _ = beta.fit(similarities_beta, floc=0, fscale=1)
    shape, _, scale = weibull_min.fit(similarities_positive, floc=0)

    print(f"Total pairs: {len(similarities):,}")
    print(f"Mean:        {np.mean(similarities):.6f}")
    print(f"Median:      {np.median(similarities):.6f}")
    print(f"Std:         {np.std(similarities):.6f}")
    print()
    print(f"Beta(alpha={alpha:.3f}, beta={beta_param:.3f})")
    print(f"Weibull(shape={shape:.3f}, scale={scale:.3f})")

    x = np.linspace(0.0, 1.0, 1_000)
    hist_bins = np.linspace(0.0, 1.0, 120)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].hist(
        similarities,
        bins=hist_bins,
        density=True,
        color="steelblue",
        alpha=0.35,
        edgecolor="none",
        label="Observed",
    )
    axes[0].plot(
        x,
        beta.pdf(x, alpha, beta_param, loc=0, scale=1),
        color="darkorange",
        linewidth=2,
        label=f"Beta({alpha:.2f}, {beta_param:.2f})",
    )
    axes[0].plot(
        x,
        weibull_min.pdf(x, shape, loc=0, scale=scale),
        color="darkgreen",
        linewidth=2,
        label=f"Weibull(c={shape:.2f}, scale={scale:.3f})",
    )
    axes[0].set_title("Distribution Fit")
    axes[0].set_xlabel("MCES similarity")
    axes[0].set_ylabel("Density")
    axes[0].legend()

    axes[1].hist(
        similarities,
        bins=hist_bins,
        density=True,
        color="steelblue",
        alpha=0.35,
        edgecolor="none",
        label="Observed",
    )
    axes[1].plot(
        x,
        beta.pdf(x, alpha, beta_param, loc=0, scale=1),
        color="darkorange",
        linewidth=2,
        label="Beta fit",
    )
    axes[1].plot(
        x,
        weibull_min.pdf(x, shape, loc=0, scale=scale),
        color="darkgreen",
        linewidth=2,
        label="Weibull fit",
    )
    axes[1].set_title("Distribution Fit (log y)")
    axes[1].set_xlabel("MCES similarity")
    axes[1].set_ylabel("Density")
    axes[1].set_yscale("log")
    axes[1].legend()

    plt.suptitle(f"RASCAL MCES distribution fit for {sample_name}", fontsize=14)
    plt.tight_layout()

    out_path = Path(f"data/results/{sample_name}_distribution_fit.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved to: {out_path}")


if __name__ == "__main__":
    main()
