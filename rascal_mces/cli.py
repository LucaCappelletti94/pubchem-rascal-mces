from pathlib import Path

import click

from .config import Config


@click.group()
@click.option("--root", type=click.Path(), default=".", help="Project root directory")
@click.pass_context
def main(ctx, root):
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config(project_root=Path(root).resolve())


@main.command()
@click.pass_context
def download(ctx):
    """Download PubChem SMILES data from FTP."""
    from .data.download import run_download

    run_download(ctx.obj["config"])


@main.command()
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Only process first N compounds (for quick preliminary runs)",
)
@click.option(
    "--cores",
    default=None,
    type=int,
    help="Number of cores for parallel normalization (default: nproc-1)",
)
@click.option(
    "--from-file",
    default=None,
    type=click.Path(exists=True),
    help="External SMILES file (TSV/CSV) instead of PubChem",
)
@click.option(
    "--source",
    default=None,
    type=click.Choice(["massspecgym", "pubchemlite"]),
    help="Fetch from a known dataset (e.g. massspecgym, pubchemlite)",
)
@click.pass_context
def prepare(ctx, limit, cores, from_file, source):
    """Parse, normalize, filter, and deduplicate compounds."""
    from .data.prepare import run_prepare

    run_prepare(
        ctx.obj["config"],
        limit=limit,
        n_cores=cores,
        from_file=from_file,
        source=source,
    )


@main.command()
@click.option("--name", required=True, help="Sample name (e.g. pilot_1k)")
@click.option("--size", default=None, type=int, help="Number of compounds to sample")
@click.option("--all", "use_all", is_flag=True, help="Use all compounds (no sampling)")
@click.pass_context
def sample(ctx, name, size, use_all):
    """Draw a stratified random sample and write compound file."""
    from .data.sample import run_sample

    run_sample(ctx.obj["config"], name=name, size=size, use_all=use_all)


@main.command()
@click.argument("compound_file", type=click.Path(exists=True))
@click.argument("chunk_id", type=int)
@click.argument("output_file", type=click.Path())
@click.pass_context
def worker(ctx, compound_file, chunk_id, output_file):
    """Process a single chunk of molecule pairs (used by SLURM array jobs)."""
    from .compute.worker import run_worker

    run_worker(ctx.obj["config"], compound_file, chunk_id, output_file)


@main.command()
@click.option("--sample-name", required=True)
@click.option(
    "--cores", default=None, type=int, help="Number of cores (default: nproc-1)"
)
@click.option(
    "--offset", default=0, type=int, help="Starting chunk ID (for multi-cluster splits)"
)
@click.option(
    "--n-chunks", default=None, type=int, help="Number of chunks to process from offset"
)
@click.pass_context
def run_local(ctx, sample_name, cores, offset, n_chunks):
    """Run all chunks locally using multiprocessing."""
    from .compute.driver import run_local_driver

    run_local_driver(
        ctx.obj["config"],
        sample_name=sample_name,
        n_cores=cores,
        offset=offset,
        n_chunks=n_chunks,
    )


@main.command()
@click.argument("result_dir", type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path())
@click.option(
    "--compound-file",
    default=None,
    type=click.Path(exists=True),
    help="Compound TSV to include as compounds.parquet",
)
@click.pass_context
def merge(ctx, result_dir, output_dir, compound_file):
    """Merge per-chunk parquet files into ~1GB output files."""
    from .postprocess.merge import run_merge

    run_merge(ctx.obj["config"], result_dir, output_dir, compound_file=compound_file)


@main.command()
@click.argument("dataset_dir", type=click.Path(exists=True))
@click.option("--title", required=True, help="Zenodo deposit title")
@click.option("--description", required=True, help="Zenodo deposit description")
@click.option("--sandbox", is_flag=True, help="Use Zenodo sandbox (for testing)")
@click.pass_context
def publish(ctx, dataset_dir, title, description, sandbox):
    """Upload a merged dataset to Zenodo and get a DOI."""
    from .postprocess.publish import run_publish

    run_publish(dataset_dir, title=title, description=description, sandbox=sandbox)
