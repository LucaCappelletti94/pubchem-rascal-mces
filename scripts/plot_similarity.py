"""Plot the distribution of MCES similarities from completed chunks.

Usage:
    uv run python scripts/plot_similarity.py [SAMPLE_NAME]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq


def main():
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "massspecgym"
    result_dir = Path(f"data/results/cluster/{sample_name}")

    chunk_files = sorted(result_dir.glob("chunk_*.parquet"))
    print(f"Reading {len(chunk_files)} chunk files...")

    similarities = []
    compute_times = []
    timed_out_flags = []

    for f in chunk_files:
        table = pq.read_table(f, columns=["similarity", "compute_time_ms", "timed_out"])
        similarities.extend(table.column("similarity").to_pylist())
        compute_times.extend(table.column("compute_time_ms").to_pylist())
        timed_out_flags.extend(table.column("timed_out").to_pylist())

    similarities = np.array(similarities, dtype=np.float32)
    compute_times = np.array(compute_times, dtype=np.float32)
    timed_out = np.array(timed_out_flags, dtype=np.int8)

    # Filter out None/NaN
    valid = ~np.isnan(similarities)
    sim_valid = similarities[valid]

    print(f"Total pairs: {len(similarities):,}")
    print(f"Valid similarities: {len(sim_valid):,}")
    print(f"Timed out: {(timed_out == 1).sum():,}")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Similarity distribution (full range)
    ax = axes[0, 0]
    ax.hist(sim_valid, bins=200, color="steelblue", edgecolor="none", alpha=0.8)
    ax.set_xlabel("MCES Similarity")
    ax.set_ylabel("Count")
    ax.set_title(f"MCES Similarity Distribution (n={len(sim_valid):,})")
    ax.set_yscale("log")
    ax.axvline(
        x=np.median(sim_valid),
        color="red",
        linestyle="--",
        alpha=0.7,
        label=f"Median: {np.median(sim_valid):.4f}",
    )
    ax.axvline(
        x=np.mean(sim_valid),
        color="orange",
        linestyle="--",
        alpha=0.7,
        label=f"Mean: {np.mean(sim_valid):.4f}",
    )
    ax.legend()

    # 2. Similarity distribution (zoomed to 0-0.5)
    ax = axes[0, 1]
    sim_low = sim_valid[sim_valid < 0.5]
    ax.hist(sim_low, bins=200, color="steelblue", edgecolor="none", alpha=0.8)
    ax.set_xlabel("MCES Similarity")
    ax.set_ylabel("Count")
    ax.set_title(
        f"Similarity < 0.5 ({100 * len(sim_low) / len(sim_valid):.1f}% of pairs)"
    )
    ax.set_yscale("log")

    # 3. Compute time distribution
    ax = axes[1, 0]
    ct_ms = compute_times[compute_times > 0]
    ax.hist(np.log10(ct_ms), bins=200, color="coral", edgecolor="none", alpha=0.8)
    ax.set_xlabel("log10(Compute Time / ms)")
    ax.set_ylabel("Count")
    ax.set_title("Compute Time Distribution")
    ax.set_yscale("log")
    ax.axvline(
        x=np.log10(60000),
        color="red",
        linestyle="--",
        alpha=0.7,
        label="60s timeout",
    )
    ax.axvline(
        x=np.log10(300000),
        color="darkred",
        linestyle="--",
        alpha=0.7,
        label="300s timeout",
    )
    ax.axvline(
        x=np.log10(600000),
        color="black",
        linestyle="--",
        alpha=0.7,
        label="600s timeout",
    )
    ax.legend()

    # 4. Similarity vs compute time (sampled)
    ax = axes[1, 1]
    n_sample = min(500_000, len(sim_valid))
    idx = np.random.default_rng(42).choice(len(sim_valid), n_sample, replace=False)
    ax.scatter(
        sim_valid[idx],
        np.log10(np.maximum(compute_times[valid][idx], 0.1)),
        s=0.1,
        alpha=0.1,
        color="steelblue",
    )
    ax.set_xlabel("MCES Similarity")
    ax.set_ylabel("log10(Compute Time / ms)")
    ax.set_title(f"Similarity vs Compute Time (n={n_sample:,} sampled)")
    ax.axhline(y=np.log10(60000), color="red", linestyle="--", alpha=0.5, label="60s")
    ax.axhline(
        y=np.log10(300000), color="darkred", linestyle="--", alpha=0.5, label="300s"
    )
    ax.legend()

    plt.suptitle(
        f"RASCAL MCES — {sample_name} (43.5% complete, {len(sim_valid):,} pairs)",
        fontsize=14,
        fontweight="bold",
    )
    plt.tight_layout()

    out_path = f"data/results/{sample_name}_similarity_analysis.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved to: {out_path}")

    # Print summary stats
    print("\n=== Similarity Summary ===")

    print(f"Mean:   {np.mean(sim_valid):.6f}")
    print(f"Median: {np.median(sim_valid):.6f}")
    print(f"Std:    {np.std(sim_valid):.6f}")
    for thresh in [0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
        frac = (sim_valid >= thresh).sum() / len(sim_valid)
        print(
            f"  >= {thresh:.1f}: {(sim_valid >= thresh).sum():>10,} ({100 * frac:.3f}%)"
        )


if __name__ == "__main__":
    main()
