#!/bin/bash
#SBATCH --job-name=rascal-mces
#SBATCH --array=0-99770%200
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --output=logs/worker_%A_%a.out
#SBATCH --error=logs/worker_%A_%a.err

# Usage:
#   cd $HOME/rascal-mces
#   mkdir -p logs
#   sbatch slurm/array_job.sh [SAMPLE_NAME]
#
# Example:
#   sbatch slurm/array_job.sh massspecgym

set -euo pipefail

SAMPLE_NAME="${1:-massspecgym}"

cd "$HOME/rascal-mces"

CHUNK_ID=$SLURM_ARRAY_TASK_ID
OUTPUT_FILE="data/results/cluster/${SAMPLE_NAME}/chunk_$(printf '%06d' $CHUNK_ID).parquet"

# Skip if already done
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
