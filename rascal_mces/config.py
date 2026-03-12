from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    project_root: Path = field(default_factory=lambda: Path.cwd())

    def __post_init__(self) -> None:
        if not isinstance(self.project_root, Path):
            self.project_root = Path(self.project_root)

    @property
    def raw_dir(self) -> Path:
        return self.project_root / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def samples_dir(self) -> Path:
        return self.project_root / "data" / "samples"

    @property
    def results_dir(self) -> Path:
        return self.project_root / "data" / "results"

    # PubChem FTP
    pubchem_smiles_url: str = (
        "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-SMILES.gz"
    )

    # Filtering
    min_heavy_atoms: int = 2
    max_heavy_atoms: int = 100

    # Sampling
    random_seed: int = 42
    stratification_bin_width: int = 5

    # Pair chunking
    chunk_size: int = 50_000

    # RASCAL MCES
    timeout_seconds: int = 120
