"""Analyze the completed chunks from a cluster run.

Usage:
    uv run python scripts/analyze_run.py [SAMPLE_NAME]
"""

import sys
from pathlib import Path

import pyarrow.parquet as pq

from rascal_mces.compute.worker import num_chunks, total_pairs

CHUNK_SIZE = 50_000


def main():
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "massspecgym"
    result_dir = Path(f"data/results/cluster/{sample_name}")
    sample_file = Path(f"data/samples/{sample_name}.tsv")

    # Count expected chunks
    n_compounds = sum(1 for _ in open(sample_file)) - 1  # minus header
    expected_pairs = total_pairs(n_compounds)
    expected_chunks = num_chunks(n_compounds, CHUNK_SIZE)

    # Find completed chunks
    chunk_files = sorted(result_dir.glob("chunk_*.parquet"))
    completed_ids = set()
    for f in chunk_files:
        chunk_id = int(f.stem.split("_")[1])
        completed_ids.add(chunk_id)

    missing_ids = set(range(expected_chunks)) - completed_ids
    n_completed = len(completed_ids)

    print(f"=== Run Analysis: {sample_name} ===")
    print(f"Compounds:        {n_compounds:,}")
    print(f"Expected pairs:   {expected_pairs:,}")
    print(f"Expected chunks:  {expected_chunks:,}")
    print(
        f"Completed chunks: {n_completed:,} ({100 * n_completed / expected_chunks:.1f}%)"
    )
    print(f"Missing chunks:   {len(missing_ids):,}")
    print()

    if not chunk_files:
        print("No completed chunks found.")
        return

    # Read all completed data
    print("Reading completed parquet files...")
    total_rows = 0
    total_timed_out = 0
    total_errors = 0
    compute_times = []
    file_sizes = []

    for f in chunk_files:
        file_sizes.append(f.stat().st_size)
        table = pq.read_table(f)
        n = len(table)
        total_rows += n

        timed_out_col = table.column("timed_out").to_pylist()
        total_timed_out += sum(1 for v in timed_out_col if v == 1)
        total_errors += sum(1 for v in timed_out_col if v == -1)

        ct = table.column("compute_time_ms").to_pylist()
        compute_times.extend(ct)

    print("\n=== Pair Statistics ===")
    print(f"Total pairs computed: {total_rows:,}")
    print(f"Expected if complete: {expected_pairs:,}")
    print(f"Coverage:             {100 * total_rows / expected_pairs:.2f}%")
    print()

    print("=== Timeout Analysis ===")
    print(
        f"Timed out pairs:  {total_timed_out:,} ({100 * total_timed_out / total_rows:.3f}%)"
    )
    print(
        f"Error pairs:      {total_errors:,} ({100 * total_errors / total_rows:.3f}%)"
    )
    print(f"Successful pairs: {total_rows - total_timed_out - total_errors:,}")
    print()

    # Compute time distribution
    compute_times.sort()
    n_times = len(compute_times)
    print("=== Compute Time Distribution ===")
    print(f"Min:    {compute_times[0]:.1f} ms")
    print(f"P25:    {compute_times[n_times // 4]:.1f} ms")
    print(f"Median: {compute_times[n_times // 2]:.1f} ms")
    print(f"P75:    {compute_times[3 * n_times // 4]:.1f} ms")
    print(f"P95:    {compute_times[int(n_times * 0.95)]:.1f} ms")
    print(f"P99:    {compute_times[int(n_times * 0.99)]:.1f} ms")
    print(f"Max:    {compute_times[-1]:.1f} ms")
    print()

    # Breakdown by time buckets
    buckets = [
        ("< 10ms", 0, 10),
        ("10ms - 100ms", 10, 100),
        ("100ms - 1s", 100, 1_000),
        ("1s - 10s", 1_000, 10_000),
        ("10s - 60s", 10_000, 60_000),
        ("60s - 300s", 60_000, 300_000),
        (">= 300s", 300_000, float("inf")),
    ]
    print("=== Time Buckets ===")
    for label, lo, hi in buckets:
        count = sum(1 for t in compute_times if lo <= t < hi)
        if count > 0:
            print(f"  {label:>15s}: {count:>10,} ({100 * count / n_times:.3f}%)")
    print()

    # File size stats
    file_sizes.sort()
    total_size = sum(file_sizes)
    print("=== File Size Stats ===")
    print(f"Total data:       {total_size / (1024**2):.1f} MB")
    print(f"Avg chunk file:   {total_size / len(file_sizes) / 1024:.1f} KB")
    print(f"Min chunk file:   {file_sizes[0] / 1024:.1f} KB")
    print(f"Max chunk file:   {file_sizes[-1] / 1024:.1f} KB")
    print()

    # Missing chunk ranges
    if missing_ids:
        missing_sorted = sorted(missing_ids)
        ranges = []
        start = missing_sorted[0]
        prev = start
        for mid in missing_sorted[1:]:
            if mid == prev + 1:
                prev = mid
            else:
                ranges.append((start, prev))
                start = mid
                prev = mid
        ranges.append((start, prev))

        print("=== Missing Chunk Ranges (first 20) ===")
        for s, e in ranges[:20]:
            if s == e:
                print(f"  {s}")
            else:
                print(f"  {s}-{e} ({e - s + 1} chunks)")
        if len(ranges) > 20:
            print(f"  ... and {len(ranges) - 20} more ranges")


if __name__ == "__main__":
    main()
