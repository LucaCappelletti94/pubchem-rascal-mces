#!/bin/bash
#SBATCH --job-name=rascal-mces
#SBATCH --account=ac_scscollab
#SBATCH --partition=lr6
#SBATCH --qos=lr_normal
#SBATCH --array=0-9976%500
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --output=/global/scratch/users/%u/rascal-mces-logs/worker_%A_%a.out
#SBATCH --error=/global/scratch/users/%u/rascal-mces-logs/worker_%A_%a.err

# Usage:
#   cd $HOME/rascal-mces
#   sbatch slurm/lrc/array_job.sh [SAMPLE_NAME] [OFFSET]
#
# Example:
#   sbatch slurm/lrc/array_job.sh massspecgym          # chunks 0..N
#   sbatch slurm/lrc/array_job.sh massspecgym 50000     # chunks 50000..50000+N
#
# Normally submitted via slurm/lrc/submit.sh which sets --array dynamically.

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SAMPLE_NAME="${1:-massspecgym}"
OFFSET="${2:-0}"

cd "$HOME/rascal-mces"

CHUNK_ID=$((SLURM_ARRAY_TASK_ID + OFFSET))
OUTPUT_FILE="data/results/cluster/${SAMPLE_NAME}/chunk_$(printf '%06d' $CHUNK_ID).parquet"

# Skip if already done (idempotent)
if [ -f "$OUTPUT_FILE" ]; then
    echo "Chunk $CHUNK_ID already done, skipping."
    exit 0
fi

mkdir -p "data/results/cluster/${SAMPLE_NAME}"

echo "Processing chunk $CHUNK_ID ..."
echo "Host: $(hostname), Start: $(date)"

uv run rascal-mces worker \
    "data/samples/${SAMPLE_NAME}.tsv" \
    "$CHUNK_ID" \
    "$OUTPUT_FILE"

echo "Done: $(date)"
