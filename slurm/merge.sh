#!/bin/bash
#SBATCH --job-name=rascal-merge
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/merge_%j.out
#SBATCH --error=logs/merge_%j.err

# Usage:
#   sbatch slurm/merge.sh [SAMPLE_NAME]

set -euo pipefail

SAMPLE_NAME="${1:-massspecgym}"

cd "$HOME/rascal-mces"

echo "Merging results for ${SAMPLE_NAME}..."
echo "Host: $(hostname), Start: $(date)"

uv run rascal-mces merge \
    "data/results/cluster/${SAMPLE_NAME}" \
    "data/results/merged/${SAMPLE_NAME}" \
    --compound-file "data/samples/${SAMPLE_NAME}.tsv"

echo "Done: $(date)"
