#!/bin/bash
# Progress monitor for LRC rascal-mces jobs.
#
# Usage:
#   bash slurm/lrc/status.sh <SAMPLE_NAME>

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

cd "$HOME/rascal-mces"

SAMPLE_NAME="${1:-massspecgym}"
SAMPLE_FILE="data/samples/${SAMPLE_NAME}.tsv"
RESULT_DIR="data/results/cluster/${SAMPLE_NAME}"
LOGS_DIR="/global/scratch/users/$USER/rascal-mces-logs"

# ------------------------------------------------------------------
# Compute expected chunk count
# ------------------------------------------------------------------
if [ -f "$SAMPLE_FILE" ]; then
    read -r N_COMPOUNDS TOTAL_PAIRS TOTAL_CHUNKS <<< "$(uv run python -c "
import csv
from rascal_mces.compute.worker import total_pairs, num_chunks
from rascal_mces.config import Config
config = Config()
with open('$SAMPLE_FILE') as f:
    n = sum(1 for _ in csv.DictReader(f, delimiter='\t'))
tp = total_pairs(n)
nc = num_chunks(n, config.chunk_size)
print(n, tp, nc)
")"
    echo "=== Sample: $SAMPLE_NAME ==="
    echo "Compounds:      $N_COMPOUNDS"
    echo "Total pairs:    $TOTAL_PAIRS"
    echo "Total chunks:   $TOTAL_CHUNKS"
else
    echo "WARNING: Sample file not found: $SAMPLE_FILE"
    TOTAL_CHUNKS="?"
fi

# ------------------------------------------------------------------
# Count completed chunks
# ------------------------------------------------------------------
COMPLETED=0
if [ -d "$RESULT_DIR" ]; then
    COMPLETED=$(find "$RESULT_DIR" -name "chunk_*.parquet" -type f | wc -l)
fi

echo "Completed:      $COMPLETED / $TOTAL_CHUNKS"

if [ "$TOTAL_CHUNKS" != "?" ] && [ "$TOTAL_CHUNKS" -gt 0 ]; then
    PCT=$(python3 -c "print(f'{100 * $COMPLETED / $TOTAL_CHUNKS:.1f}%')")
    echo "Progress:       $PCT"
fi

# ------------------------------------------------------------------
# SLURM queue status
# ------------------------------------------------------------------
echo ""
echo "=== SLURM Queue ==="
squeue -u "$USER" -o "%.10i %.20j %.8T %.10M %.6D %.4C %.6m %R" 2>/dev/null || echo "(squeue not available)"

# ------------------------------------------------------------------
# Recent errors
# ------------------------------------------------------------------
echo ""
echo "=== Recent Errors (last 5 non-empty .err files) ==="
if [ -d "$LOGS_DIR" ]; then
    # Find non-empty .err files, sorted by modification time (newest first)
    ERR_FILES=$(find "$LOGS_DIR" -name "worker_*.err" -size +0c -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -5 | awk '{print $2}')

    if [ -z "$ERR_FILES" ]; then
        echo "(no errors found)"
    else
        for f in $ERR_FILES; do
            echo "--- $(basename "$f") ---"
            tail -5 "$f"
            echo ""
        done
    fi
else
    echo "(logs directory not found: $LOGS_DIR)"
fi
