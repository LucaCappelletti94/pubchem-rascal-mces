#!/bin/bash
# Smart submission wrapper for LRC array jobs.
# Each array task uses a full node to process CHUNKS_PER_NODE chunks in parallel.
#
# Usage:
#   bash slurm/lrc/submit.sh <SAMPLE_NAME> [OPTIONS]
#
# Options:
#   --partition=PART       Override partition (default: lr6)
#   --offset=N             Starting chunk ID offset (default: 0)
#   --n-chunks=N           Limit number of chunks to submit
#   --chunks-per-node=N    Chunks processed per node (default: 16)
#   --concurrency=N        Max concurrent array tasks (default: 500)
#   --debug                Submit 1 node (24 chunks) on lr4 with lr_debug QoS
#   --dry-run              Show what would be submitted without actually submitting

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

cd "$HOME/rascal-mces"

# ------------------------------------------------------------------
# Parse arguments
# ------------------------------------------------------------------
SAMPLE_NAME=""
PARTITION="lr6"
QOS="lr_normal"
OFFSET=0
N_CHUNKS=""
CHUNKS_PER_NODE=16
CONCURRENCY=500
DEBUG=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --partition=*)       PARTITION="${arg#*=}" ;;
        --offset=*)          OFFSET="${arg#*=}" ;;
        --n-chunks=*)        N_CHUNKS="${arg#*=}" ;;
        --chunks-per-node=*) CHUNKS_PER_NODE="${arg#*=}" ;;
        --concurrency=*)     CONCURRENCY="${arg#*=}" ;;
        --debug)             DEBUG=true ;;
        --dry-run)           DRY_RUN=true ;;
        -*)                  echo "Unknown option: $arg"; exit 1 ;;
        *)                   SAMPLE_NAME="$arg" ;;
    esac
done

if [ -z "$SAMPLE_NAME" ]; then
    echo "Usage: bash slurm/lrc/submit.sh <SAMPLE_NAME> [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --partition=PART       Partition (default: lr6)"
    echo "  --offset=N             Starting chunk ID offset (default: 0)"
    echo "  --n-chunks=N           Limit number of chunks"
    echo "  --chunks-per-node=N    Chunks per node (default: 16)"
    echo "  --concurrency=N        Max concurrent tasks (default: 500)"
    echo "  --debug                1 node (24 chunks) on lr4 with lr_debug QoS"
    echo "  --dry-run              Show submission without executing"
    exit 1
fi

SAMPLE_FILE="data/samples/${SAMPLE_NAME}.tsv"
if [ ! -f "$SAMPLE_FILE" ]; then
    echo "ERROR: Sample file not found: $SAMPLE_FILE"
    exit 1
fi

# ------------------------------------------------------------------
# Compute chunk count (pure bash)
# ------------------------------------------------------------------
CHUNK_SIZE=50000
N_COMPOUNDS=$(( $(wc -l < "$SAMPLE_FILE") - 1 ))
TOTAL_PAIRS=$(( N_COMPOUNDS * (N_COMPOUNDS - 1) / 2 ))
TOTAL_CHUNKS=$(( (TOTAL_PAIRS + CHUNK_SIZE - 1) / CHUNK_SIZE ))
MAX_ARRAY_SIZE=1000

# ------------------------------------------------------------------
# Debug mode overrides
# ------------------------------------------------------------------
TIME="24:00:00"
if [ "$DEBUG" = true ]; then
    PARTITION="lr4"
    QOS="lr_debug"
    TIME="03:00:00"
    CHUNKS_PER_NODE=24  # lr4 has 24 cores
    N_CHUNKS=$CHUNKS_PER_NODE  # just 1 node
    CONCURRENCY=1
    echo "=== DEBUG MODE (1 node, $CHUNKS_PER_NODE chunks) ==="
fi

# ------------------------------------------------------------------
# Determine how many chunks to process and how many array tasks
# ------------------------------------------------------------------
CHUNKS_TO_PROCESS=$((TOTAL_CHUNKS - OFFSET))
if [ -n "$N_CHUNKS" ] && [ "$N_CHUNKS" -lt "$CHUNKS_TO_PROCESS" ]; then
    CHUNKS_TO_PROCESS=$N_CHUNKS
fi

if [ "$CHUNKS_TO_PROCESS" -le 0 ]; then
    echo "No chunks to process (offset $OFFSET >= total $TOTAL_CHUNKS)."
    exit 0
fi

# Number of array tasks = ceil(chunks / chunks_per_node)
N_ARRAY_TASKS=$(( (CHUNKS_TO_PROCESS + CHUNKS_PER_NODE - 1) / CHUNKS_PER_NODE ))
ARRAY_MAX=$((N_ARRAY_TASKS - 1))

# ------------------------------------------------------------------
# Count completed chunks
# ------------------------------------------------------------------
RESULT_DIR="data/results/cluster/${SAMPLE_NAME}"
COMPLETED=0
if [ -d "$RESULT_DIR" ]; then
    COMPLETED=$(find "$RESULT_DIR" -name "chunk_*.parquet" -type f | wc -l)
fi

# ------------------------------------------------------------------
# Cost estimate (lr6: $0.0075/core-hr * 40 cores * 24hr per node)
# ------------------------------------------------------------------
COST_PER_NODE=$(( 40 * 24 * 75 / 10000 ))  # ~$7.20/node
COST_EST="\$$(( N_ARRAY_TASKS * COST_PER_NODE ))"

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "=== Submission Summary ==="
echo "Sample:            $SAMPLE_NAME"
echo "Compounds:         $N_COMPOUNDS"
echo "Total pairs:       $TOTAL_PAIRS"
echo "Chunk size:        $CHUNK_SIZE"
echo "Total chunks:      $TOTAL_CHUNKS"
echo "Completed:         $COMPLETED"
echo "Chunks to process: $CHUNKS_TO_PROCESS"
echo "Chunks per node:   $CHUNKS_PER_NODE"
echo "Array tasks:       $N_ARRAY_TASKS (nodes)"
echo "Partition:         $PARTITION"
echo "QoS:               $QOS"
echo "Est. cost:         $COST_EST (worst-case at lr6 rates)"
echo ""

# ------------------------------------------------------------------
# Submit in batches of MAX_ARRAY_SIZE
# ------------------------------------------------------------------
N_BATCHES=$(( (N_ARRAY_TASKS + MAX_ARRAY_SIZE - 1) / MAX_ARRAY_SIZE ))
SUBMITTED=0
BATCH_CHUNK_OFFSET=$OFFSET

while [ "$SUBMITTED" -lt "$N_ARRAY_TASKS" ]; do
    BATCH_SIZE=$((N_ARRAY_TASKS - SUBMITTED))
    if [ "$BATCH_SIZE" -gt "$MAX_ARRAY_SIZE" ]; then
        BATCH_SIZE=$MAX_ARRAY_SIZE
    fi
    BATCH_ARRAY_MAX=$((BATCH_SIZE - 1))

    SBATCH_CMD=(
        sbatch
        --partition="$PARTITION"
        --qos="$QOS"
        --time="$TIME"
        --array="0-${BATCH_ARRAY_MAX}%${CONCURRENCY}"
        slurm/lrc/array_job.sh "$SAMPLE_NAME" "$BATCH_CHUNK_OFFSET" "$CHUNKS_PER_NODE"
    )

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] Batch $((SUBMITTED / MAX_ARRAY_SIZE + 1))/$N_BATCHES: ${SBATCH_CMD[*]}"
    else
        echo "Batch $((SUBMITTED / MAX_ARRAY_SIZE + 1))/$N_BATCHES (tasks=$BATCH_SIZE, chunk_offset=$BATCH_CHUNK_OFFSET)..."
        "${SBATCH_CMD[@]}"
    fi

    SUBMITTED=$((SUBMITTED + BATCH_SIZE))
    BATCH_CHUNK_OFFSET=$((BATCH_CHUNK_OFFSET + BATCH_SIZE * CHUNKS_PER_NODE))
done
