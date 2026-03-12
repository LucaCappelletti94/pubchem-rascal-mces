import csv
import multiprocessing
import os
from pathlib import Path

from ..config import Config
from .worker import num_chunks


def _run_worker_task(args: tuple[str, int, str, str, int, int]) -> str | None:
    """Run worker in a subprocess-isolated function. Returns error message or None."""
    compound_file, chunk_id, output_file, project_root, timeout, chunk_size = args
    try:
        from ..config import Config
        from .worker import run_worker

        config = Config(project_root=Path(project_root))
        config.timeout_seconds = timeout
        config.chunk_size = chunk_size
        run_worker(config, compound_file, chunk_id, output_file)
        return None
    except Exception as e:
        return f"FAILED: chunk {chunk_id}: {e}"


def run_local_driver(
    config: Config,
    *,
    sample_name: str,
    n_cores: int | None = None,
    offset: int = 0,
    n_chunks: int | None = None,
) -> None:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if n_chunks is not None and n_chunks <= 0:
        raise ValueError("n_chunks must be > 0")

    if n_cores is None:
        n_cores = os.cpu_count() or 1

    sample_file = config.samples_dir / f"{sample_name}.tsv"
    result_dir = config.results_dir / "local" / sample_name
    result_dir.mkdir(parents=True, exist_ok=True)

    if not sample_file.exists():
        raise FileNotFoundError(f"Sample file not found: {sample_file}")

    # Count compounds to determine number of chunks
    with open(sample_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        n_compounds = sum(1 for _ in reader)

    n_total_chunks = num_chunks(n_compounds, config.chunk_size)
    if n_total_chunks == 0:
        print(f"Sample '{sample_name}' has no chunkable pairs")
        return

    if offset >= n_total_chunks:
        print(
            f"Requested offset {offset} is beyond the last available chunk "
            f"({n_total_chunks - 1})"
        )
        return

    requested_end = n_total_chunks if n_chunks is None else offset + n_chunks
    chunk_end = min(requested_end, n_total_chunks)
    print(
        f"Sample '{sample_name}': {n_compounds} compounds, {n_total_chunks} total chunks"
    )
    if offset > 0 or n_chunks is not None:
        print(f"Processing chunks {offset}..{chunk_end - 1}")
    print(f"Using {n_cores} cores")

    # Filter to only unfinished chunks
    skipped = 0
    tasks = []
    for chunk_id in range(offset, chunk_end):
        output_file = result_dir / f"chunk_{chunk_id:06d}.parquet"
        if output_file.exists():
            skipped += 1
            continue
        tasks.append(
            (
                str(sample_file),
                chunk_id,
                str(output_file),
                str(config.project_root),
                config.timeout_seconds,
                config.chunk_size,
            )
        )

    if skipped:
        print(f"Skipping {skipped} already-completed chunks")

    if not tasks:
        if offset > 0 or n_chunks is not None:
            print("All requested chunks already processed!")
        else:
            print("All chunks already processed!")
        return

    print(f"Processing {len(tasks)} remaining chunks ...")

    with multiprocessing.Pool(n_cores) as pool:
        failures = 0
        for result in pool.imap_unordered(_run_worker_task, tasks):
            if result is not None:
                print(result)
                failures += 1

    completed = len(tasks) - failures
    print(
        f"\nDone: {completed} chunks completed, {failures} failed. Results in {result_dir}"
    )
