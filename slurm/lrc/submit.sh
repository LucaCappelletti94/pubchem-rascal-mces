#!/bin/bash
# Smart submission wrapper for LRC array jobs.
# Reads the sample TSV, computes chunk count, skips completed chunks.
#
# Usage:
#   bash slurm/lrc/submit.sh <SAMPLE_NAME> [OPTIONS]
#
# Options:
#   --partition=PART   Override partition (default: lr6)
#   --offset=N         Starting chunk ID offset (default: 0)
#   --n-chunks=N       Limit number of chunks to submit
#   --concurrency=N    Max concurrent array tasks (default: 500)
#   --debug            Submit 3 chunks on lr4 (free) with lr_debug QoS
#   --dry-run          Show what would be submitted without actually submitting

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
CONCURRENCY=500
DEBUG=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --partition=*) PARTITION="${arg#*=}" ;;
        --offset=*)    OFFSET="${arg#*=}" ;;
        --n-chunks=*)  N_CHUNKS="${arg#*=}" ;;
        --concurrency=*) CONCURRENCY="${arg#*=}" ;;
        --debug)       DEBUG=true ;;
        --dry-run)     DRY_RUN=true ;;
        -*)            echo "Unknown option: $arg"; exit 1 ;;
        *)             SAMPLE_NAME="$arg" ;;
    esac
done

if [ -z "$SAMPLE_NAME" ]; then
    echo "Usage: bash slurm/lrc/submit.sh <SAMPLE_NAME> [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --partition=PART   Partition (default: lr6)"
    echo "  --offset=N         Starting chunk ID offset (default: 0)"
    echo "  --n-chunks=N       Limit number of chunks"
    echo "  --concurrency=N    Max concurrent tasks (default: 500)"
    echo "  --debug            3 chunks on lr4 (free) with lr_debug QoS"
    echo "  --dry-run          Show submission without executing"
    exit 1
fi

SAMPLE_FILE="data/samples/${SAMPLE_NAME}.tsv"
if [ ! -f "$SAMPLE_FILE" ]; then
    echo "ERROR: Sample file not found: $SAMPLE_FILE"
    exit 1
fi

# ------------------------------------------------------------------
# Compute chunk count from sample file using Python helpers
# ------------------------------------------------------------------
read -r N_COMPOUNDS TOTAL_PAIRS TOTAL_CHUNKS CHUNK_SIZE <<< "$(uv run python -c "
import csv
from rascal_mces.compute.worker import total_pairs, num_chunks
from rascal_mces.config import Config
config = Config()
with open('$SAMPLE_FILE') as f:
    n = sum(1 for _ in csv.DictReader(f, delimiter='\t'))
tp = total_pairs(n)
nc = num_chunks(n, config.chunk_size)
print(n, tp, nc, config.chunk_size)
")"

# ------------------------------------------------------------------
# Debug mode overrides
# ------------------------------------------------------------------
if [ "$DEBUG" = true ]; then
    PARTITION="lr4"
    QOS="lr_debug"
    N_CHUNKS=3
    CONCURRENCY=3
    echo "=== DEBUG MODE ==="
fi

# ------------------------------------------------------------------
# Determine array range
# ------------------------------------------------------------------
if [ -n "$N_CHUNKS" ]; then
    ARRAY_MAX=$((N_CHUNKS - 1))
else
    ARRAY_MAX=$((TOTAL_CHUNKS - 1 - OFFSET))
fi

# Cap to total chunks available
MAX_POSSIBLE=$((TOTAL_CHUNKS - 1 - OFFSET))
if [ "$ARRAY_MAX" -gt "$MAX_POSSIBLE" ]; then
    ARRAY_MAX=$MAX_POSSIBLE
fi

if [ "$ARRAY_MAX" -lt 0 ]; then
    echo "No chunks to process (offset $OFFSET >= total $TOTAL_CHUNKS)."
    exit 0
fi

# ------------------------------------------------------------------
# Count completed chunks
# ------------------------------------------------------------------
RESULT_DIR="data/results/cluster/${SAMPLE_NAME}"
COMPLETED=0
if [ -d "$RESULT_DIR" ]; then
    COMPLETED=$(find "$RESULT_DIR" -name "chunk_*.parquet" -type f | wc -l)
fi

# ------------------------------------------------------------------
# Cost estimate (lr6: $0.0075/core-hr, 4hr wall time per task)
# ------------------------------------------------------------------
REMAINING=$((ARRAY_MAX + 1))
COST_EST=$(python3 -c "print(f'\${:.0f}'.format($REMAINING * 4 * 0.0075))" 2>/dev/null || echo "N/A")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "=== Submission Summary ==="
echo "Sample:         $SAMPLE_NAME"
echo "Compounds:      $N_COMPOUNDS"
echo "Total pairs:    $TOTAL_PAIRS"
echo "Chunk size:     $CHUNK_SIZE"
echo "Total chunks:   $TOTAL_CHUNKS"
echo "Completed:      $COMPLETED"
echo "Offset:         $OFFSET"
echo "Array range:    0-${ARRAY_MAX}%${CONCURRENCY}"
echo "Partition:      $PARTITION"
echo "QoS:            $QOS"
echo "Est. cost:      $COST_EST (worst-case at lr6 rates)"
echo ""

# ------------------------------------------------------------------
# Submit
# ------------------------------------------------------------------
SBATCH_CMD=(
    sbatch
    --partition="$PARTITION"
    --qos="$QOS"
    --array="0-${ARRAY_MAX}%${CONCURRENCY}"
    slurm/lrc/array_job.sh "$SAMPLE_NAME" "$OFFSET"
)

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would execute:"
    echo "  ${SBATCH_CMD[*]}"
    exit 0
fi

echo "Submitting..."
"${SBATCH_CMD[@]}"
