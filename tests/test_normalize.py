"""Tests for MolNormalizer and basic RASCAL MCES functionality."""

from rdkit.Chem import MolFromSmiles, MolToSmiles
from rdkit.Chem.rdRascalMCES import FindMCES, RascalOptions

from rascal_mces.normalize import MolNormalizer


def test_normalizer_inchi_simple():
    """Normalize a simple organic molecule from InChI (caffeine)."""
    normalizer = MolNormalizer()
    mol = normalizer.normalize_inchi(
        "InChI=1S/C8H10N4O2/c1-10-4-9-6-5(10)7(13)12(3)8(14)11(6)2/h4H,1-3H3"
    )
    assert mol is not None
    smi = MolToSmiles(mol)
    assert "n" in smi or "N" in smi


def test_normalizer_smiles_simple():
    """Normalize a simple organic molecule from SMILES (caffeine)."""
    normalizer = MolNormalizer()
    mol = normalizer.normalize_smiles("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
    assert mol is not None
    smi = MolToSmiles(mol)
    assert "n" in smi or "N" in smi


def test_normalizer_smiles_salt_stripping():
    """Normalization should strip salts and keep the largest organic fragment."""
    normalizer = MolNormalizer()
    # Diphenhydramine hydrochloride as SMILES
    mol = normalizer.normalize_smiles("C(COCN(C)C)(c1ccccc1)c1ccccc1.Cl")
    assert mol is not None
    smi = MolToSmiles(mol)
    assert "Cl" not in smi


def test_normalizer_smiles_invalid():
    """Invalid SMILES should return None."""
    normalizer = MolNormalizer()
    assert normalizer.normalize_smiles("not_a_smiles") is None
    assert normalizer.normalize_smiles("") is None


def test_normalizer_inchi_invalid():
    """Invalid InChI should return None."""
    normalizer = MolNormalizer()
    assert normalizer.normalize_inchi("not_an_inchi") is None
    assert normalizer.normalize_inchi("") is None


def test_normalizer_suppresses_rdkit_rejection_logs(capfd):
    """Rejected molecules should not leak RDKit parser errors to stderr."""
    normalizer = MolNormalizer()

    assert normalizer.normalize_smiles("not_a_smiles") is None
    assert normalizer.normalize_smiles("c1nccc2ccccn12") is None

    captured = capfd.readouterr()
    assert captured.err == ""


def test_normalizer_single_atom():
    """Single heavy atom molecule should normalize fine."""
    normalizer = MolNormalizer()
    mol = normalizer.normalize_smiles("C")
    assert mol is not None


def test_rascal_mces_trivial_pair():
    """RASCAL MCES should work on a trivial pair of molecules."""
    mol1 = MolFromSmiles("c1ccccc1")  # benzene
    mol2 = MolFromSmiles("c1ccc(O)cc1")  # phenol

    opts = RascalOptions()
    opts.similarityThreshold = 0.0
    opts.returnEmptyMCES = True
    opts.timeout = 30

    results = FindMCES(mol1, mol2, opts)
    assert len(results) > 0
    r = results[0]
    assert r.similarity > 0
    assert not r.timedOut


def test_rascal_mces_identical():
    """Identical molecules should have similarity 1.0."""
    mol = MolFromSmiles("c1ccccc1")

    opts = RascalOptions()
    opts.similarityThreshold = 0.0
    opts.returnEmptyMCES = True
    opts.timeout = 30

    results = FindMCES(mol, mol, opts)
    assert len(results) > 0
    assert abs(results[0].similarity - 1.0) < 1e-6


def test_rascal_mces_dissimilar():
    """Very different molecules should have low similarity."""
    mol1 = MolFromSmiles("C")  # methane
    mol2 = MolFromSmiles("c1ccc2ccccc2c1")  # naphthalene

    opts = RascalOptions()
    opts.similarityThreshold = 0.0
    opts.returnEmptyMCES = True
    opts.timeout = 30

    results = FindMCES(mol1, mol2, opts)
    assert len(results) > 0
    assert results[0].similarity < 0.5
