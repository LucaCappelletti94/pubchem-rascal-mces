from __future__ import annotations

import gzip
import multiprocessing
import os
from pathlib import Path
from typing import TYPE_CHECKING

from tqdm import tqdm

from ..config import Config

if TYPE_CHECKING:
    from ..normalize import MolNormalizer

_normalizer: MolNormalizer | None = None


def _init_worker() -> None:
    """Initialize per-process normalizer (avoid pickling RDKit objects)."""
    global _normalizer
    from rdkit import RDLogger

    RDLogger.logger().setLevel(RDLogger.ERROR)

    from ..normalize import MolNormalizer

    _normalizer = MolNormalizer()


def _normalize_smiles(raw_smiles: str) -> tuple[str, str, int] | None:
    """Normalize a SMILES string. Returns (InChIKey, canonical_SMILES, HAC) or None."""
    from rdkit.Chem import MolToSmiles, MolToInchi
    from rdkit.Chem.inchi import InchiToInchiKey

    raw_smiles = raw_smiles.strip()
    if not raw_smiles:
        return None

    assert _normalizer is not None
    mol = _normalizer.normalize_smiles(raw_smiles)
    if mol is None:
        return None

    hac = mol.GetNumHeavyAtoms()
    smiles = MolToSmiles(mol)
    norm_inchi = MolToInchi(mol)
    if norm_inchi is None:
        return None
    inchi_key = InchiToInchiKey(norm_inchi)

    return (inchi_key, smiles, hac)


def _process_pubchem_line(line: str) -> tuple[int, str, str, int] | None:
    """Parse a PubChem CID<TAB>SMILES line and normalize."""
    line = line.strip()
    if not line:
        return None
    parts = line.split("\t", 1)
    if len(parts) != 2:
        return None
    cid_str, raw_smiles = parts
    try:
        cid = int(cid_str)
    except ValueError:
        return None
    result = _normalize_smiles(raw_smiles)
    if result is None:
        return None
    inchi_key, smiles, hac = result
    return (cid, inchi_key, smiles, hac)


def _process_external_item(item: tuple[int, str]) -> tuple[int, str, str, int] | None:
    """Normalize an (id, SMILES) tuple."""
    idx, raw_smiles = item
    result = _normalize_smiles(raw_smiles)
    if result is None:
        return None
    inchi_key, smiles, hac = result
    return (idx, inchi_key, smiles, hac)


def _read_pubchem(config: Config, limit: int | None) -> list[str]:
    smiles_gz = config.raw_dir / "CID-SMILES.gz"
    if not smiles_gz.exists():
        raise FileNotFoundError(
            f"Run 'rascal-mces download' first. Missing: {smiles_gz}"
        )
    print(f"Reading {smiles_gz} ...")
    lines = []
    with gzip.open(smiles_gz, "rt", encoding="utf-8") as f:
        for line in f:
            lines.append(line)
            if limit is not None and len(lines) >= limit:
                break
    return lines


def _read_external_file(path: Path) -> list[tuple[int, str]]:
    """Read a TSV/CSV file with SMILES. Supports formats:
    - One SMILES per line
    - TSV with header containing a 'smiles' or 'SMILES' column
    - TSV with ID<TAB>SMILES (no header)
    """
    items = []
    with open(path) as f:
        first_line = f.readline().strip()
        # Detect header
        lower = first_line.lower()
        if "smiles" in lower:
            # Has header — find the SMILES column
            headers = (
                first_line.split("\t") if "\t" in first_line else first_line.split(",")
            )
            headers_lower = [h.lower().strip() for h in headers]
            smiles_col = next(i for i, h in enumerate(headers_lower) if "smiles" in h)
            for idx, line in enumerate(f):
                parts = (
                    line.strip().split("\t")
                    if "\t" in line
                    else line.strip().split(",")
                )
                if smiles_col < len(parts):
                    items.append((idx, parts[smiles_col].strip()))
        else:
            # No header — try ID<TAB>SMILES or just SMILES
            parts = first_line.split("\t")
            if len(parts) >= 2:
                items.append((0, parts[-1].strip()))
                for idx, line in enumerate(f, 1):
                    p = line.strip().split("\t")
                    items.append((idx, p[-1].strip()))
            else:
                items.append((0, first_line))
                for idx, line in enumerate(f, 1):
                    items.append((idx, line.strip()))
    return items


_HF_SOURCES = {
    "massspecgym": "roman-bushuiev/MassSpecGym",
}

KNOWN_SOURCES = list(_HF_SOURCES) + ["pubchemlite"]


def _fetch_source(
    source: str, *, config: Config, limit: int | None = None
) -> list[tuple[int, str]]:
    """Fetch unique SMILES from a known dataset."""
    if source not in KNOWN_SOURCES:
        raise ValueError(f"Unknown source '{source}'. Known sources: {KNOWN_SOURCES}")

    if source == "pubchemlite":
        return _fetch_pubchemlite(config, limit)

    hf_id = _HF_SOURCES[source]
    print(f"Fetching '{source}' from HuggingFace ({hf_id}) ...")

    from datasets import load_dataset

    ds = load_dataset(hf_id, split="val", streaming=True)
    smiles_set: set[str] = set()
    for row in tqdm(ds, desc="Reading", unit=" spectra"):
        smi = row["smiles"]
        if smi:
            smiles_set.add(smi)
        if limit is not None and len(smiles_set) >= limit:
            break

    print(f"Found {len(smiles_set):,} unique SMILES")
    return list(enumerate(sorted(smiles_set)))


def _fetch_pubchemlite(
    config: Config, limit: int | None = None
) -> list[tuple[int, str]]:
    """Download PubChemLite CSV from Zenodo and extract (CID, SMILES) pairs."""
    import csv
    import json
    import urllib.request

    raw_dir = config.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Use cached file if available
    cached = sorted(raw_dir.glob("PubChemLite_*.csv"))
    if cached:
        csv_path = cached[-1]
        print(f"Using cached PubChemLite: {csv_path}")
    else:
        record_id = config.pubchemlite_zenodo_record
        api_url = f"https://zenodo.org/api/records/{record_id}/files"
        print(f"Fetching file list from Zenodo record {record_id} ...")
        with urllib.request.urlopen(api_url) as resp:
            data = json.loads(resp.read())
        csv_entry = next(e for e in data["entries"] if e["key"].endswith(".csv"))
        download_url = csv_entry["links"]["content"]
        filename = csv_entry["key"]
        csv_path = raw_dir / filename
        size_mb = csv_entry["size"] / 1e6
        print(f"Downloading {filename} ({size_mb:.1f} MB) ...")
        from .download import _download_with_progress

        _download_with_progress(download_url, csv_path)

    print(f"Reading {csv_path} ...")
    items: list[tuple[int, str]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="Reading PubChemLite", unit=" compounds"):
            cid = int(row["Identifier"])
            smiles = row["SMILES"]
            if smiles:
                items.append((cid, smiles))
            if limit is not None and len(items) >= limit:
                break

    print(f"Read {len(items):,} compounds from PubChemLite")
    return items


def run_prepare(
    config: Config,
    *,
    limit: int | None = None,
    n_cores: int | None = None,
    from_file: str | None = None,
    source: str | None = None,
) -> None:
    config.processed_dir.mkdir(parents=True, exist_ok=True)

    if n_cores is None:
        n_cores = os.cpu_count() or 1

    output = config.processed_dir / "pubchem_clean.tsv"

    if source is not None:
        items = _fetch_source(source, config=config, limit=limit)
        _run_prepare_items(config, output, items, n_cores)
    elif from_file is not None:
        _run_prepare_external(config, output, Path(from_file), n_cores, limit)
    else:
        _run_prepare_pubchem(config, output, n_cores, limit)


def _run_prepare_pubchem(
    config: Config, output: Path, n_cores: int, limit: int | None
) -> None:
    lines = _read_pubchem(config, limit)
    total = len(lines)
    print(f"Loaded {total:,} lines. Normalizing with {n_cores} cores ...")

    norm_fail = 0
    filtered_size = 0
    duplicates = 0
    unique_keys: dict[str, tuple[int, str, str, int]] = {}

    with multiprocessing.Pool(n_cores, initializer=_init_worker) as pool:
        for result in tqdm(
            pool.imap(_process_pubchem_line, lines, chunksize=1024),
            total=total,
            desc="Normalizing",
            unit=" compounds",
            mininterval=2.0,
        ):
            if result is None:
                norm_fail += 1
                continue
            cid, inchi_key, smiles, hac = result
            if hac < config.min_heavy_atoms or hac > config.max_heavy_atoms:
                filtered_size += 1
                continue
            if inchi_key in unique_keys:
                duplicates += 1
                if cid < unique_keys[inchi_key][0]:
                    unique_keys[inchi_key] = (cid, inchi_key, smiles, hac)
            else:
                unique_keys[inchi_key] = (cid, inchi_key, smiles, hac)

    _write_output(output, unique_keys, total, norm_fail, filtered_size, duplicates)


def _run_prepare_external(
    config: Config, output: Path, from_file: Path, n_cores: int, limit: int | None
) -> None:
    print(f"Reading external file {from_file} ...")
    items = _read_external_file(from_file)
    if limit is not None:
        items = items[:limit]
    _run_prepare_items(config, output, items, n_cores)


def _run_prepare_items(
    config: Config,
    output: Path,
    items: list[tuple[int, str]],
    n_cores: int,
) -> None:
    total = len(items)
    print(f"Loaded {total:,} molecules. Normalizing with {n_cores} cores ...")

    norm_fail = 0
    filtered_size = 0
    duplicates = 0
    unique_keys: dict[str, tuple[int, str, str, int]] = {}

    with multiprocessing.Pool(n_cores, initializer=_init_worker) as pool:
        for result in tqdm(
            pool.imap(_process_external_item, items, chunksize=256),
            total=total,
            desc="Normalizing",
            unit=" compounds",
            mininterval=2.0,
        ):
            if result is None:
                norm_fail += 1
                continue
            idx, inchi_key, smiles, hac = result
            if hac < config.min_heavy_atoms or hac > config.max_heavy_atoms:
                filtered_size += 1
                continue
            if inchi_key in unique_keys:
                duplicates += 1
            else:
                unique_keys[inchi_key] = (idx, inchi_key, smiles, hac)

    # Re-number IDs sequentially (external files may not have meaningful IDs)
    renumbered: dict[str, tuple[int, str, str, int]] = {}
    for new_id, (inchi_key, (_, _, smiles, hac)) in enumerate(
        sorted(unique_keys.items()), 1
    ):
        renumbered[inchi_key] = (new_id, inchi_key, smiles, hac)
    _write_output(output, renumbered, total, norm_fail, filtered_size, duplicates)


def _write_output(
    output: Path,
    unique_keys: dict[str, tuple[int, str, str, int]],
    total: int,
    norm_fail: int,
    filtered_size: int,
    duplicates: int,
) -> None:
    print(f"Writing {len(unique_keys):,} unique compounds to {output} ...")
    sorted_compounds = sorted(unique_keys.values(), key=lambda x: x[0])

    with open(output, "w") as out:
        out.write("CID\tInChIKey\tSMILES\tHeavyAtomCount\n")
        for cid, inchi_key, smiles, hac in sorted_compounds:
            out.write(f"{cid}\t{inchi_key}\t{smiles}\t{hac}\n")

    clean_count = len(unique_keys)
    print("\n=== Preparation Report ===")
    print(f"Total compounds processed:  {total:,}")
    print(f"Normalization failures:     {norm_fail:,} ({norm_fail / total * 100:.2f}%)")
    print(
        f"Filtered by size:           {filtered_size:,} ({filtered_size / total * 100:.2f}%)"
    )
    print(
        f"Duplicates removed:         {duplicates:,} ({duplicates / total * 100:.2f}%)"
    )
    print(f"Final clean compounds:      {clean_count:,}")
    print(f"Output: {output}")
