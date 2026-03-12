"""Tests for the Parquet worker."""

import os
import tempfile

import pyarrow.parquet as pq

from rascal_mces.compute.worker import (
    num_chunks,
    pairs_for_chunk,
    run_worker,
    total_pairs,
)
from rascal_mces.config import Config


def _make_compound_file(path: str) -> None:
    with open(path, "w") as f:
        f.write("CID\tInChIKey\tSMILES\tHeavyAtomCount\n")
        f.write("1\tABC\tc1ccccc1\t6\n")  # benzene
        f.write("2\tDEF\tc1ccc(O)cc1\t7\n")  # phenol
        f.write("3\tGHI\tCCO\t2\n")  # ethanol


def test_worker_produces_parquet():
    with tempfile.TemporaryDirectory() as tmpdir:
        compound_file = os.path.join(tmpdir, "compounds.tsv")
        output_file = os.path.join(tmpdir, "output.parquet")

        _make_compound_file(compound_file)

        config = Config()
        config.chunk_size = 100  # all 3 pairs in one chunk
        run_worker(config, compound_file, 0, output_file)

        assert os.path.exists(output_file)
        table = pq.read_table(output_file)
        assert len(table) == 3
        assert set(table.column_names) == {
            "cid_a",
            "cid_b",
            "similarity",
            "timed_out",
            "compute_time_ms",
        }

        # Benzene vs phenol should have high similarity
        sims = dict(
            zip(
                [
                    (a, b)
                    for a, b in zip(
                        table.column("cid_a").to_pylist(),
                        table.column("cid_b").to_pylist(),
                    )
                ],
                table.column("similarity").to_pylist(),
            )
        )
        assert sims[(1, 2)] > 0.5  # benzene-phenol are similar


def test_worker_no_timeouts_on_small_molecules():
    with tempfile.TemporaryDirectory() as tmpdir:
        compound_file = os.path.join(tmpdir, "compounds.tsv")
        output_file = os.path.join(tmpdir, "output.parquet")

        _make_compound_file(compound_file)

        config = Config()
        config.chunk_size = 100
        run_worker(config, compound_file, 0, output_file)

        table = pq.read_table(output_file)
        timeouts = table.column("timed_out").to_pylist()
        assert all(t == 0 for t in timeouts)


def test_total_pairs():
    assert total_pairs(3) == 3
    assert total_pairs(10) == 45
    assert total_pairs(100) == 4950


def test_num_chunks():
    assert num_chunks(3, 100) == 1  # 3 pairs fits in 1 chunk
    assert num_chunks(10, 10) == 5  # 45 pairs / 10 = 5 chunks
    assert num_chunks(10, 45) == 1  # exact fit


def test_pairs_for_chunk_covers_all():
    """All chunks together should produce every pair exactly once."""
    cids = list(range(20))
    n = len(cids)
    chunk_size = 7
    n_chunks = num_chunks(n, chunk_size)

    all_pairs = []
    for chunk_id in range(n_chunks):
        all_pairs.extend(pairs_for_chunk(cids, chunk_id, chunk_size))

    # Should cover all N*(N-1)/2 pairs
    assert len(all_pairs) == total_pairs(n)
    # No duplicates
    assert len(set(all_pairs)) == len(all_pairs)
    # Each pair (i, j) has i < j
    assert all(a < b for a, b in all_pairs)


def test_pairs_for_chunk_out_of_range():
    cids = list(range(5))
    assert pairs_for_chunk(cids, 999, 100) == []
