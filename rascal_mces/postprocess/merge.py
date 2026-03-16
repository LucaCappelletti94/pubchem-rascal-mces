import csv
import json
import platform
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import rdkit

from ..config import Config


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

    out_file = output_path / "pairs.parquet"
    writer = None
    total_rows = 0

    for chunk_file in chunk_files:
        table = pq.read_table(chunk_file)
        if writer is None:
            writer = pq.ParquetWriter(str(out_file), table.schema, compression="zstd")
        writer.write_table(table)
        total_rows += len(table)

    if writer is not None:
        writer.close()
    out_size = out_file.stat().st_size
    print(f"  pairs.parquet: {total_rows:,} rows ({out_size / (1024**3):.2f} GB)")

    # Write metadata
    metadata = {
        "rdkit_version": rdkit.__version__,
        "timeout_seconds": config.timeout_seconds,
        "hostname": platform.node(),
        "cpu": platform.processor() or "unknown",
        "total_pairs": total_rows,
        "chunk_count": len(chunk_files),
    }
    meta_path = output_path / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMerged {total_rows:,} total pairs into {out_file}")
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
