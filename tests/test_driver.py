"""Tests for the local chunk driver and CLI forwarding."""

from pathlib import Path
from typing import Literal

import pytest
from click.testing import CliRunner

from rascal_mces.cli import main
from rascal_mces.compute import driver
from rascal_mces.config import Config


def _make_sample_file(path: Path, n_compounds: int) -> None:
    with open(path, "w") as f:
        f.write("CID\tInChIKey\tSMILES\tHeavyAtomCount\n")
        for cid in range(1, n_compounds + 1):
            f.write(f"{cid}\tKEY{cid}\tCC\t2\n")


def test_run_local_driver_limits_requested_chunk_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sample_dir = tmp_path / "data" / "samples"
    sample_dir.mkdir(parents=True)
    _make_sample_file(sample_dir / "demo.tsv", n_compounds=6)

    submitted_tasks: list[tuple[str, int, str, str, int, int]] = []

    class FakePool:
        def __init__(self, n_cores: int) -> None:
            self.n_cores = n_cores

        def __enter__(self) -> "FakePool":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> Literal[False]:
            return False

        def imap_unordered(self, func, tasks):
            submitted_tasks.extend(tasks)
            for _ in tasks:
                yield None

    monkeypatch.setattr(driver.multiprocessing, "Pool", FakePool)

    config = Config(project_root=tmp_path)
    config.chunk_size = 2
    driver.run_local_driver(config, sample_name="demo", n_cores=2, offset=2, n_chunks=3)

    assert [task[1] for task in submitted_tasks] == [2, 3, 4]
    assert "Processing chunks 2..4" in capsys.readouterr().out


def test_run_local_driver_skips_completed_chunks_in_requested_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_dir = tmp_path / "data" / "samples"
    result_dir = tmp_path / "data" / "results" / "local" / "demo"
    sample_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    _make_sample_file(sample_dir / "demo.tsv", n_compounds=6)
    (result_dir / "chunk_000003.parquet").touch()

    submitted_tasks: list[tuple[str, int, str, str, int, int]] = []

    class FakePool:
        def __init__(self, n_cores: int) -> None:
            self.n_cores = n_cores

        def __enter__(self) -> "FakePool":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> Literal[False]:
            return False

        def imap_unordered(self, func, tasks):
            submitted_tasks.extend(tasks)
            for _ in tasks:
                yield None

    monkeypatch.setattr(driver.multiprocessing, "Pool", FakePool)

    config = Config(project_root=tmp_path)
    config.chunk_size = 2
    driver.run_local_driver(config, sample_name="demo", n_cores=2, offset=2, n_chunks=3)

    assert [task[1] for task in submitted_tasks] == [2, 4]


def test_run_local_driver_rejects_invalid_ranges(tmp_path: Path) -> None:
    config = Config(project_root=tmp_path)

    with pytest.raises(ValueError, match="offset must be >= 0"):
        driver.run_local_driver(config, sample_name="demo", offset=-1)

    with pytest.raises(ValueError, match="n_chunks must be > 0"):
        driver.run_local_driver(config, sample_name="demo", n_chunks=0)


def test_run_local_driver_reports_out_of_range_offset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sample_dir = tmp_path / "data" / "samples"
    sample_dir.mkdir(parents=True)
    _make_sample_file(sample_dir / "demo.tsv", n_compounds=4)

    config = Config(project_root=tmp_path)
    config.chunk_size = 10
    driver.run_local_driver(config, sample_name="demo", offset=1)

    assert (
        "Requested offset 1 is beyond the last available chunk (0)"
        in capsys.readouterr().out
    )


def test_run_local_cli_passes_chunk_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run_local_driver(
        config: Config,
        *,
        sample_name: str,
        n_cores: int | None = None,
        offset: int = 0,
        n_chunks: int | None = None,
    ) -> None:
        captured["project_root"] = config.project_root
        captured["sample_name"] = sample_name
        captured["n_cores"] = n_cores
        captured["offset"] = offset
        captured["n_chunks"] = n_chunks

    monkeypatch.setattr(driver, "run_local_driver", fake_run_local_driver)

    result = CliRunner().invoke(
        main,
        [
            "--root",
            str(tmp_path),
            "run-local",
            "--sample-name",
            "demo",
            "--cores",
            "3",
            "--offset",
            "7",
            "--n-chunks",
            "11",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "project_root": tmp_path.resolve(),
        "sample_name": "demo",
        "n_cores": 3,
        "offset": 7,
        "n_chunks": 11,
    }
