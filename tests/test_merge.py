"""Tests for the merge module."""

import json
import os
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from rascal_mces.config import Config
from rascal_mces.postprocess.merge import run_merge


def _make_chunk_parquet(path: str, n: int, offset: int = 0) -> None:
    table = pa.table(
        {
            "cid_a": pa.array(list(range(offset, offset + n)), type=pa.int32()),
            "cid_b": pa.array(list(range(offset + 1, offset + n + 1)), type=pa.int32()),
            "similarity": pa.array([0.3] * n, type=pa.float32()),
            "timed_out": pa.array([0] * n, type=pa.int8()),
            "compute_time_ms": pa.array([1.0] * n, type=pa.float32()),
        }
    )
    pq.write_table(table, path, compression="zstd")


def test_merge_combines_chunks():
    with tempfile.TemporaryDirectory() as tmpdir:
        chunk_dir = os.path.join(tmpdir, "chunks")
        output_dir = os.path.join(tmpdir, "merged")
        os.makedirs(chunk_dir)

        _make_chunk_parquet(os.path.join(chunk_dir, "chunk_0000.parquet"), 100)
        _make_chunk_parquet(
            os.path.join(chunk_dir, "chunk_0001.parquet"), 100, offset=100
        )
        _make_chunk_parquet(
            os.path.join(chunk_dir, "chunk_0002.parquet"), 50, offset=200
        )

        config = Config(project_root=tmpdir)
        run_merge(config, chunk_dir, output_dir)

        # Check output
        assert os.path.exists(os.path.join(output_dir, "metadata.json"))
        pairs_file = os.path.join(output_dir, "pairs.parquet")
        assert os.path.exists(pairs_file)

        # Check total rows
        t = pq.read_table(pairs_file)
        assert len(t) == 250

        # Check metadata
        with open(os.path.join(output_dir, "metadata.json")) as f:
            meta = json.load(f)
        assert meta["total_pairs"] == 250
        assert meta["chunk_count"] == 3
