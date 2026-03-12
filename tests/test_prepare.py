"""Tests for the prepare module."""

import os
import tempfile
from pathlib import Path

import pytest
from rdkit import RDLogger

import rascal_mces.data.prepare as prepare_module
import rascal_mces.normalize as normalize_module
from rascal_mces.config import Config
from rascal_mces.data.prepare import run_prepare


def _make_smiles_file(path: str) -> None:
    with open(path, "w") as f:
        f.write("smiles\n")
        f.write("c1ccccc1\n")  # benzene
        f.write("CCO\n")  # ethanol
        f.write("c1ccc(O)cc1\n")  # phenol
        f.write("INVALID_SMILES\n")
        f.write("CC(=O)O\n")  # acetic acid


def test_prepare_from_external_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(project_root=tmpdir)
        smiles_file = os.path.join(tmpdir, "test_smiles.tsv")
        _make_smiles_file(smiles_file)

        run_prepare(config, from_file=smiles_file, n_cores=1)

        output = config.processed_dir / "pubchem_clean.tsv"
        assert output.exists()

        with open(output) as f:
            lines = f.readlines()

        # Header + valid compounds (benzene, ethanol, phenol, acetic acid)
        # INVALID_SMILES should be filtered out
        header = lines[0].strip()
        assert "CID" in header
        assert "SMILES" in header
        assert "InChIKey" in header
        assert len(lines) >= 4  # header + at least 3 valid molecules


def test_prepare_deduplicates():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(project_root=tmpdir)
        smiles_file = os.path.join(tmpdir, "dup_smiles.tsv")

        with open(smiles_file, "w") as f:
            f.write("smiles\n")
            f.write("c1ccccc1\n")  # benzene
            f.write("C1=CC=CC=C1\n")  # benzene (different notation)
            f.write("CCO\n")  # ethanol

        run_prepare(config, from_file=smiles_file, n_cores=1)

        output = config.processed_dir / "pubchem_clean.tsv"
        with open(output) as f:
            lines = f.readlines()

        # Two benzene notations should deduplicate to one
        assert len(lines) == 3  # header + 2 unique compounds


def test_prepare_filters_by_size():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(project_root=tmpdir)
        config.min_heavy_atoms = 3
        config.max_heavy_atoms = 10

        smiles_file = os.path.join(tmpdir, "size_smiles.tsv")
        with open(smiles_file, "w") as f:
            f.write("smiles\n")
            f.write("C\n")  # methane: 1 heavy atom -> filtered
            f.write("c1ccccc1\n")  # benzene: 6 heavy atoms -> kept
            f.write("c1ccc2ccccc2c1\n")  # naphthalene: 10 heavy atoms -> kept

        run_prepare(config, from_file=smiles_file, n_cores=1)

        output = config.processed_dir / "pubchem_clean.tsv"
        with open(output) as f:
            lines = f.readlines()

        assert len(lines) == 3  # header + benzene + naphthalene


def test_run_prepare_uses_all_detected_cores_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run_prepare_external(
        config: Config,
        output: Path,
        from_file: Path,
        n_cores: int,
        limit: int | None,
    ) -> None:
        captured["project_root"] = config.project_root
        captured["output"] = output
        captured["from_file"] = from_file
        captured["n_cores"] = n_cores
        captured["limit"] = limit

    monkeypatch.setattr(prepare_module.os, "cpu_count", lambda: 5)
    monkeypatch.setattr(
        prepare_module, "_run_prepare_external", fake_run_prepare_external
    )

    config = Config(project_root=tmp_path)
    from_file = tmp_path / "input.tsv"
    run_prepare(config, from_file=str(from_file))

    assert captured == {
        "project_root": tmp_path.resolve(),
        "output": config.processed_dir / "pubchem_clean.tsv",
        "from_file": from_file,
        "n_cores": 5,
        "limit": None,
    }


def test_init_worker_sets_rdkit_logger_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    levels: list[int] = []

    class FakeLogger:
        def setLevel(self, level: int) -> None:
            levels.append(level)

    class FakeNormalizer:
        pass

    monkeypatch.setattr(RDLogger, "logger", lambda: FakeLogger())
    monkeypatch.setattr(normalize_module, "MolNormalizer", FakeNormalizer)
    monkeypatch.setattr(prepare_module, "_normalizer", None)

    prepare_module._init_worker()

    assert levels == [RDLogger.ERROR]
    assert isinstance(prepare_module._normalizer, FakeNormalizer)
