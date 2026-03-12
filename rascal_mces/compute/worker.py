import csv
import math
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from rdkit.Chem import MolFromSmiles
from rdkit.Chem.rdRascalMCES import FindMCES, RascalOptions

from ..config import Config

SCHEMA = pa.schema(
    [
        ("cid_a", pa.int32()),
        ("cid_b", pa.int32()),
        ("similarity", pa.float32()),
        ("timed_out", pa.int8()),
        ("compute_time_ms", pa.float32()),
    ]
)

BATCH_SIZE = 1000


def total_pairs(n: int) -> int:
    return n * (n - 1) // 2


def num_chunks(n_compounds: int, chunk_size: int) -> int:
    return math.ceil(total_pairs(n_compounds) / chunk_size)


def pairs_for_chunk(
    cids: list[int], chunk_id: int, chunk_size: int
) -> list[tuple[int, int]]:
    """Compute the pairs for a given chunk by index into the upper triangle."""
    n = len(cids)
    start = chunk_id * chunk_size
    end = min(start + chunk_size, total_pairs(n))

    if start >= total_pairs(n):
        return []

    # Find starting row: cumulative pairs before row i = i*n - i*(i+1)/2
    def _cum(i: int) -> int:
        return i * n - i * (i + 1) // 2

    disc = (2 * n - 1) ** 2 - 8 * start
    row = max(0, int((2 * n - 1 - math.isqrt(max(disc, 0))) // 2))
    # Adjust: isqrt may overshoot, so step back if needed
    while row > 0 and _cum(row) > start:
        row -= 1
    while row + 1 < n and _cum(row + 1) <= start:
        row += 1

    pairs = []
    idx = row * n - row * (row + 1) // 2  # cumulative pairs before this row

    for i in range(row, n - 1):
        row_start = idx
        row_size = n - 1 - i
        row_end = idx + row_size

        if row_end <= start:
            idx = row_end
            continue

        j_lo = max(0, start - row_start)
        j_hi = min(row_size, end - row_start)

        for j_offset in range(j_lo, j_hi):
            pairs.append((cids[i], cids[i + 1 + j_offset]))

        idx = row_end
        if idx >= end:
            break

    return pairs


def run_worker(
    config: Config, compound_file: str, chunk_id: int, output_file: str
) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load compounds (sorted by CID for deterministic triangle ordering)
    compounds: dict[int, object] = {}
    with open(compound_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            cid = int(row["CID"])
            mol = MolFromSmiles(row["SMILES"])
            if mol is not None:
                compounds[cid] = mol

    cids = sorted(compounds.keys())
    pairs = pairs_for_chunk(cids, chunk_id, config.chunk_size)

    print(
        f"Worker chunk {chunk_id}: {len(compounds)} compounds, {len(pairs)} pairs -> {output_path}"
    )

    if not pairs:
        print("No pairs for this chunk, skipping.")
        return

    opts = RascalOptions()
    opts.similarityThreshold = 0.0  # type: ignore[assignment]
    opts.timeout = config.timeout_seconds  # type: ignore[assignment]
    opts.returnEmptyMCES = True  # type: ignore[assignment]
    opts.maxBondMatchPairs = 5000  # type: ignore[assignment]

    cid_a_buf: list[int] = []
    cid_b_buf: list[int] = []
    sim_buf: list[float | None] = []
    timeout_buf: list[int] = []
    time_buf: list[float] = []

    processed = 0
    t_start = time.monotonic()

    writer = None

    for cid_a, cid_b in pairs:
        mol_a = compounds[cid_a]
        mol_b = compounds[cid_b]

        t0 = time.perf_counter()
        try:
            res_list = FindMCES(mol_a, mol_b, opts)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if res_list:
                r = res_list[0]
                cid_a_buf.append(cid_a)
                cid_b_buf.append(cid_b)
                sim_buf.append(r.similarity)
                timeout_buf.append(1 if r.timedOut else 0)
                time_buf.append(elapsed_ms)
            else:
                cid_a_buf.append(cid_a)
                cid_b_buf.append(cid_b)
                sim_buf.append(0.0)
                timeout_buf.append(0)
                time_buf.append(elapsed_ms)
        except Exception:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            cid_a_buf.append(cid_a)
            cid_b_buf.append(cid_b)
            sim_buf.append(None)
            timeout_buf.append(-1)
            time_buf.append(elapsed_ms)

        processed += 1

        if len(cid_a_buf) >= BATCH_SIZE:
            batch = _make_batch(cid_a_buf, cid_b_buf, sim_buf, timeout_buf, time_buf)
            if writer is None:
                writer = pq.ParquetWriter(str(output_path), SCHEMA, compression="zstd")
            writer.write_table(batch)
            cid_a_buf, cid_b_buf, sim_buf, timeout_buf, time_buf = [], [], [], [], []

            if processed % 5000 == 0:
                elapsed = time.monotonic() - t_start
                rate = processed / elapsed
                print(f"  [{processed}/{len(pairs)}] {rate:.1f} pairs/sec")

    # Flush remaining
    if cid_a_buf:
        batch = _make_batch(cid_a_buf, cid_b_buf, sim_buf, timeout_buf, time_buf)
        if writer is None:
            writer = pq.ParquetWriter(str(output_path), SCHEMA, compression="zstd")
        writer.write_table(batch)

    if writer is not None:
        writer.close()

    elapsed = time.monotonic() - t_start
    print(
        f"Worker done: {processed} pairs in {elapsed:.1f}s ({processed / elapsed:.1f} pairs/sec)"
    )


def _make_batch(cid_a, cid_b, sim, timeout, time_ms) -> pa.Table:
    return pa.table(
        {
            "cid_a": pa.array(cid_a, type=pa.int32()),
            "cid_b": pa.array(cid_b, type=pa.int32()),
            "similarity": pa.array(sim, type=pa.float32()),
            "timed_out": pa.array(timeout, type=pa.int8()),
            "compute_time_ms": pa.array(time_ms, type=pa.float32()),
        }
    )
