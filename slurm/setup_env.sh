#!/bin/bash
# Setup the rascal-mces environment on the cluster.
# Run this ONCE on a login node.

set -euo pipefail

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

cd "$HOME/rascal-mces"

# Create venv and install
uv sync
echo "Environment ready. Test with:"
echo "  uv run rascal-mces --help"
echo "  uv run python -c 'from rdkit.Chem import rdRascalMCES; print(\"RASCAL OK\")'"
