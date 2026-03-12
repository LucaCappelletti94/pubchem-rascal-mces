#!/bin/bash
#SBATCH --job-name=rascal-merge
#SBATCH --account=ac_scscollab
#SBATCH --partition=lr6
#SBATCH --qos=lr_normal
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=04:00:00
#SBATCH --output=/global/scratch/users/%u/rascal-mces-logs/merge_%j.out
#SBATCH --error=/global/scratch/users/%u/rascal-mces-logs/merge_%j.err

# Usage:
#   cd $HOME/rascal-mces
#   sbatch slurm/lrc/merge.sh [SAMPLE_NAME]

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SAMPLE_NAME="${1:-massspecgym}"

cd "$HOME/rascal-mces"

echo "Merging results for ${SAMPLE_NAME}..."
echo "Host: $(hostname), Start: $(date)"

uv run rascal-mces merge \
    "data/results/cluster/${SAMPLE_NAME}" \
    "data/results/merged/${SAMPLE_NAME}" \
    --compound-file "data/samples/${SAMPLE_NAME}.tsv"

echo "Done: $(date)"
