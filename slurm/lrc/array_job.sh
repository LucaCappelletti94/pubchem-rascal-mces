#!/bin/bash
#SBATCH --job-name=rascal-mces
#SBATCH --account=ac_scscollab
#SBATCH --partition=lr6
#SBATCH --qos=lr_normal
#SBATCH --array=0-311%500
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=04:00:00
#SBATCH --output=/global/scratch/users/%u/rascal-mces-logs/worker_%A_%a.out
#SBATCH --error=/global/scratch/users/%u/rascal-mces-logs/worker_%A_%a.err

# Each array task processes CHUNKS_PER_NODE chunks in parallel (one per core).
# This packs a full lr6 node efficiently instead of wasting 31/32 cores.
#
# Usage (normally called via submit.sh):
#   sbatch slurm/lrc/array_job.sh [SAMPLE_NAME] [OFFSET] [CHUNKS_PER_NODE]

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SAMPLE_NAME="${1:-massspecgym}"
OFFSET="${2:-0}"
CHUNKS_PER_NODE="${3:-$(nproc)}"

cd "$HOME/rascal-mces"

# This array task handles chunks [BATCH_START, BATCH_END)
BATCH_START=$(( SLURM_ARRAY_TASK_ID * CHUNKS_PER_NODE + OFFSET ))
BATCH_END=$(( BATCH_START + CHUNKS_PER_NODE ))

echo "Node $(hostname): processing chunks ${BATCH_START}..${BATCH_END}-1 (${CHUNKS_PER_NODE} parallel)"
echo "Start: $(date)"

mkdir -p "data/results/cluster/${SAMPLE_NAME}"

# Launch one worker per chunk in parallel
PIDS=()
for (( CHUNK_ID=BATCH_START; CHUNK_ID<BATCH_END; CHUNK_ID++ )); do
    OUTPUT_FILE="data/results/cluster/${SAMPLE_NAME}/chunk_$(printf '%06d' $CHUNK_ID).parquet"

    # Skip if already done
    if [ -f "$OUTPUT_FILE" ]; then
        echo "Chunk $CHUNK_ID already done, skipping."
        continue
    fi

    uv run rascal-mces worker \
        "data/samples/${SAMPLE_NAME}.tsv" \
        "$CHUNK_ID" \
        "$OUTPUT_FILE" &
    PIDS+=($!)
done

# Wait for all workers and track failures
FAILURES=0
for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        FAILURES=$((FAILURES + 1))
    fi
done

echo "Done: $(date), failures: $FAILURES/${#PIDS[@]}"
if [ "$FAILURES" -gt 0 ]; then
    exit 1
fi
