import csv
import random

import click

from ..config import Config
from ..compute.worker import num_chunks, total_pairs


def run_sample(
    config: Config, *, name: str, size: int | None = None, use_all: bool = False
) -> None:
    config.samples_dir.mkdir(parents=True, exist_ok=True)

    clean_file = config.processed_dir / "pubchem_clean.tsv"
    if not clean_file.exists():
        raise FileNotFoundError(
            f"Run 'rascal-mces prepare' first. Missing: {clean_file}"
        )

    # Read all compounds
    compounds = []
    with open(clean_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            compounds.append(row)

    print(f"Loaded {len(compounds):,} compounds from {clean_file}")

    if use_all:
        compounds.sort(key=lambda x: int(x["CID"]))
        return _write_sample(config, name, compounds)

    if size is None:
        raise click.UsageError("Either --size or --all must be specified")

    if size > len(compounds):
        raise ValueError(
            f"Requested {size} but only {len(compounds)} compounds available"
        )

    # Stratified sampling by heavy atom count
    rng = random.Random(config.random_seed)
    bin_width = config.stratification_bin_width

    # Bin compounds
    bins: dict[int, list[dict]] = {}
    for comp in compounds:
        hac = int(comp["HeavyAtomCount"])
        bin_id = hac // bin_width
        bins.setdefault(bin_id, []).append(comp)

    # Proportional allocation
    total_compounds = len(compounds)
    sampled: list[dict] = []

    sorted_bin_ids = sorted(bins.keys())
    allocations = {}
    for bin_id in sorted_bin_ids:
        bin_compounds = bins[bin_id]
        alloc = max(1, round(len(bin_compounds) / total_compounds * size))
        alloc = min(alloc, len(bin_compounds))
        allocations[bin_id] = alloc

    # Adjust to hit exact target
    total_alloc = sum(allocations.values())
    if total_alloc > size:
        # Trim from largest bins
        for bin_id in sorted(allocations, key=lambda b: allocations[b], reverse=True):
            if total_alloc <= size:
                break
            reduce = min(allocations[bin_id] - 1, total_alloc - size)
            allocations[bin_id] -= reduce
            total_alloc -= reduce
    elif total_alloc < size:
        # Add to largest bins
        for bin_id in sorted(allocations, key=lambda b: len(bins[b]), reverse=True):
            if total_alloc >= size:
                break
            can_add = len(bins[bin_id]) - allocations[bin_id]
            add = min(can_add, size - total_alloc)
            allocations[bin_id] += add
            total_alloc += add

    for bin_id in sorted_bin_ids:
        bin_compounds = bins[bin_id]
        n = allocations.get(bin_id, 0)
        if n > 0:
            chosen = rng.sample(bin_compounds, n)
            sampled.extend(chosen)

    # Sort by CID for deterministic output
    sampled.sort(key=lambda x: int(x["CID"]))

    _write_sample(config, name, sampled)


def _write_sample(config: Config, name: str, sampled: list[dict]) -> None:
    bin_width = config.stratification_bin_width

    # Write sample compound file
    sample_file = config.samples_dir / f"{name}.tsv"
    with open(sample_file, "w") as f:
        f.write("CID\tInChIKey\tSMILES\tHeavyAtomCount\n")
        for comp in sampled:
            f.write(
                f"{comp['CID']}\t{comp['InChIKey']}\t{comp['SMILES']}\t{comp['HeavyAtomCount']}\n"
            )

    n = len(sampled)
    n_pairs = total_pairs(n)
    n_chunks = num_chunks(n, config.chunk_size)

    print(f"Selected {n:,} compounds -> {sample_file}")
    print(f"Total pairs: {n_pairs:,}")
    print(f"Chunks of {config.chunk_size:,}: {n_chunks:,}")

    # Print bin distribution
    print(f"\nHeavy atom distribution (bin width={bin_width}):")
    sample_bins: dict[int, int] = {}
    for comp in sampled:
        bin_id = int(comp["HeavyAtomCount"]) // bin_width
        sample_bins[bin_id] = sample_bins.get(bin_id, 0) + 1
    for bin_id in sorted(sample_bins):
        lo = bin_id * bin_width
        hi = lo + bin_width - 1
        print(f"  [{lo:3d}-{hi:3d}]: {sample_bins[bin_id]:,}")
