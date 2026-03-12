from rdkit.Chem import Mol, MolFromInchi, MolFromSmiles
from rdkit.Chem.MolStandardize.rdMolStandardize import (
    LargestFragmentChooser,
    MetalDisconnector,
    Normalizer,
    Reionizer,
    Uncharger,
)


class MolNormalizer:
    def __init__(self):
        self._disconnector = MetalDisconnector()
        self._normalizer = Normalizer()
        self._reionizer = Reionizer()
        self._chooser = LargestFragmentChooser(preferOrganic=True)
        self._uncharger = Uncharger(canonicalOrder=True)

    def normalize_mol(self, mol: Mol) -> Mol | None:
        try:
            mol = self._disconnector.Disconnect(mol)
            mol = self._normalizer.normalize(mol)
            mol = self._reionizer.reionize(mol)
            mol = self._chooser.choose(mol)
            mol = self._uncharger.uncharge(mol)
            return mol
        except Exception:
            return None

    def normalize_inchi(self, inchi: str) -> Mol | None:
        try:
            mol = MolFromInchi(inchi, sanitize=True, removeHs=True)
            if mol is None:
                return None
            return self.normalize_mol(mol)
        except Exception:
            return None

    def normalize_smiles(self, smiles: str) -> Mol | None:
        try:
            if not smiles:
                return None
            mol = MolFromSmiles(smiles)
            if mol is None:
                return None
            return self.normalize_mol(mol)
        except Exception:
            return None
