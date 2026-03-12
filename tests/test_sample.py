"""Tests for sampling."""

import csv
import tempfile

from rascal_mces.config import Config
from rascal_mces.data.sample import run_sample


def _make_clean_file(path: str, n: int = 100) -> None:
    with open(path, "w") as f:
        f.write("CID\tInChIKey\tSMILES\tHeavyAtomCount\n")
        for i in range(1, n + 1):
            hac = 5 + (i % 20)
            f.write(f"{i}\tKEY{i:04d}\tC{'C' * hac}\t{hac}\n")


def test_sample_stratified():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(project_root=tmpdir)
        config.processed_dir.mkdir(parents=True)
        config.samples_dir.mkdir(parents=True)

        _make_clean_file(str(config.processed_dir / "pubchem_clean.tsv"), n=200)

        run_sample(config, name="test_20", size=20)

        sample_file = config.samples_dir / "test_20.tsv"
        assert sample_file.exists()

        with open(sample_file) as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        assert len(rows) == 20
        # CIDs should be sorted
        cids = [int(r["CID"]) for r in rows]
        assert cids == sorted(cids)


def test_sample_all():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(project_root=tmpdir)
        config.processed_dir.mkdir(parents=True)
        config.samples_dir.mkdir(parents=True)

        _make_clean_file(str(config.processed_dir / "pubchem_clean.tsv"), n=50)

        run_sample(config, name="test_all", use_all=True)

        sample_file = config.samples_dir / "test_all.tsv"
        assert sample_file.exists()

        with open(sample_file) as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        assert len(rows) == 50
