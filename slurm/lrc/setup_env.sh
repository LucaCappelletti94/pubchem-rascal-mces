#!/bin/bash
# One-time setup for pubchem-rascal-mces on LBNL Lawrencium (LRC).
# Run on a login node: bash slurm/lrc/setup_env.sh

set -euo pipefail

REPO_URL="https://github.com/LucaCappelletti94/pubchem-rascal-mces.git"
REPO_DIR="$HOME/rascal-mces"
SCRATCH="/global/scratch/users/$USER"
DATA_DIR="$SCRATCH/rascal-mces-data"
LOGS_DIR="$SCRATCH/rascal-mces-logs"

# ------------------------------------------------------------------
# 1. Install uv if not present
# ------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv: $(uv --version)"

# ------------------------------------------------------------------
# 2. Clone or update the repo
# ------------------------------------------------------------------
if [ -d "$REPO_DIR/.git" ]; then
    echo "Repo exists, pulling latest..."
    git -C "$REPO_DIR" pull --ff-only
else
    echo "Cloning repo..."
    git clone "$REPO_URL" "$REPO_DIR"
fi

# ------------------------------------------------------------------
# 3. Create SCRATCH directories
# ------------------------------------------------------------------
echo "Creating scratch directories..."
mkdir -p "$DATA_DIR"/{raw,processed,samples,results/cluster,results/merged}
mkdir -p "$LOGS_DIR"

# ------------------------------------------------------------------
# 4. Symlink data/ and logs/ to SCRATCH
# ------------------------------------------------------------------
for link_name in data logs; do
    target_dir="$DATA_DIR"
    if [ "$link_name" = "logs" ]; then
        target_dir="$LOGS_DIR"
    fi

    link_path="$REPO_DIR/$link_name"

    if [ -L "$link_path" ]; then
        echo "Symlink $link_name already exists -> $(readlink "$link_path")"
    elif [ -d "$link_path" ]; then
        echo "ERROR: $link_path is a real directory, not a symlink."
        echo "Move or remove it manually before running this script."
        exit 1
    else
        ln -s "$target_dir" "$link_path"
        echo "Created symlink: $link_name -> $target_dir"
    fi
done

# ------------------------------------------------------------------
# 5. Install dependencies
# ------------------------------------------------------------------
cd "$REPO_DIR"
echo "Running uv sync..."
uv sync

# ------------------------------------------------------------------
# 6. Verify CLI and RASCAL import
# ------------------------------------------------------------------
echo ""
echo "=== Verification ==="

if uv run rascal-mces --help > /dev/null 2>&1; then
    echo "CLI: OK"
else
    echo "CLI: FAIL"
    exit 1
fi

if uv run python -c 'from rdkit.Chem import rdRascalMCES; print("RASCAL: OK")'; then
    :
else
    echo "RASCAL: FAIL"
    exit 1
fi

echo ""
echo "Setup complete. Next steps:"
echo "  1. Transfer sample data:  bash slurm/lrc/transfer_data.sh <sample_name>  (from local)"
echo "  2. Debug run:             bash slurm/lrc/submit.sh <sample_name> --debug"
echo "  3. Production run:        bash slurm/lrc/submit.sh <sample_name>"
