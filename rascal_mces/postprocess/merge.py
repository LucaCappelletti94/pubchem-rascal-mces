import csv
import json
import platform
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import rdkit

from ..config import Config

TARGET_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB


def run_merge(
    config: Config, result_dir: str, output_dir: str, compound_file: str | None = None
) -> None:
    result_path = Path(result_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    chunk_files = sorted(result_path.glob("chunk_*.parquet"))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk parquet files found in {result_path}")

    print(f"Merging {len(chunk_files)} chunk files -> {output_path}/")

    # Write compounds.parquet if compound file provided
    if compound_file is not None:
        _write_compounds_parquet(compound_file, output_path)

    # Estimate rows per output file based on first chunk
    sample_table = pq.read_table(chunk_files[0])
    sample_size = chunk_files[0].stat().st_size
    rows_in_sample = len(sample_table)
    if sample_size > 0 and rows_in_sample > 0:
        bytes_per_row = sample_size / rows_in_sample
        rows_per_file = int(TARGET_FILE_SIZE / bytes_per_row)
    else:
        rows_per_file = 50_000_000  # fallback ~50M rows

    print(f"Target: ~{rows_per_file:,} rows per output file (~1 GB)")

    total_rows = 0
    output_idx = 0
    writer = None
    rows_in_current = 0

    for chunk_file in chunk_files:
        table = pq.read_table(chunk_file)
        n = len(table)
        total_rows += n

        if writer is None:
            out_file = output_path / f"pairs_{output_idx:04d}.parquet"
            writer = pq.ParquetWriter(str(out_file), table.schema, compression="zstd")

        writer.write_table(table)
        rows_in_current += n

        if rows_in_current >= rows_per_file:
            writer.close()
            out_size = (output_path / f"pairs_{output_idx:04d}.parquet").stat().st_size
            print(
                f"  pairs_{output_idx:04d}.parquet: {rows_in_current:,} rows ({out_size / (1024**2):.1f} MB)"
            )
            output_idx += 1
            writer = None
            rows_in_current = 0

    if writer is not None:
        writer.close()
        out_file = output_path / f"pairs_{output_idx:04d}.parquet"
        out_size = out_file.stat().st_size
        print(
            f"  pairs_{output_idx:04d}.parquet: {rows_in_current:,} rows ({out_size / (1024**2):.1f} MB)"
        )
        output_idx += 1

    # Write metadata
    metadata = {
        "rdkit_version": rdkit.__version__,
        "timeout_seconds": config.timeout_seconds,
        "hostname": platform.node(),
        "cpu": platform.processor() or "unknown",
        "total_pairs": total_rows,
        "chunk_count": len(chunk_files),
        "output_files": output_idx,
    }
    meta_path = output_path / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(
        f"\nMerged {total_rows:,} total pairs into {output_idx} files in {output_path}"
    )
    print(f"Metadata: {meta_path}")


def _write_compounds_parquet(compound_file: str, output_path: Path) -> None:
    """Convert compound TSV to Parquet for inclusion in published dataset."""
    rows: list[dict[str, str]] = []
    with open(compound_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    table = pa.table(
        {
            "cid": pa.array([int(r["CID"]) for r in rows], type=pa.int32()),
            "inchikey": pa.array([r["InChIKey"] for r in rows], type=pa.string()),
            "smiles": pa.array([r["SMILES"] for r in rows], type=pa.string()),
            "heavy_atom_count": pa.array(
                [int(r["HeavyAtomCount"]) for r in rows], type=pa.int16()
            ),
        }
    )

    out = output_path / "compounds.parquet"
    pq.write_table(table, str(out), compression="zstd")
    print(
        f"  compounds.parquet: {len(table):,} compounds ({out.stat().st_size / 1024:.1f} KB)"
    )
