#!/bin/bash
# Progress monitor for LRC rascal-mces jobs.
#
# Usage:
#   bash slurm/lrc/status.sh <SAMPLE_NAME> [INTERVAL]
#
# Runs once by default. Pass an interval in seconds to watch continuously:
#   bash slurm/lrc/status.sh massspecgym 30

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

cd "$HOME/rascal-mces"

SAMPLE_NAME="${1:-massspecgym}"
INTERVAL="${2:-}"
SAMPLE_FILE="data/samples/${SAMPLE_NAME}.tsv"
RESULT_DIR="data/results/cluster/${SAMPLE_NAME}"
LOGS_DIR="/global/scratch/users/$USER/rascal-mces-logs"

# ------------------------------------------------------------------
# Compute expected chunk count (once, outside the loop)
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
else
    echo "WARNING: Sample file not found: $SAMPLE_FILE"
    N_COMPOUNDS="?"
    TOTAL_PAIRS="?"
    TOTAL_CHUNKS="?"
fi

show_status() {
    clear
    echo "=== Sample: $SAMPLE_NAME === ($(date '+%H:%M:%S'))"
    echo "Compounds:      $N_COMPOUNDS"
    echo "Total pairs:    $TOTAL_PAIRS"
    echo "Total chunks:   $TOTAL_CHUNKS"

    # Count completed chunks
    local completed=0
    if [ -d "$RESULT_DIR" ]; then
        completed=$(find "$RESULT_DIR" -name "chunk_*.parquet" -type f | wc -l)
    fi

    echo "Completed:      $completed / $TOTAL_CHUNKS"

    if [ "$TOTAL_CHUNKS" != "?" ] && [ "$TOTAL_CHUNKS" -gt 0 ]; then
        python3 -c "print(f'Progress:       {100 * $completed / $TOTAL_CHUNKS:.1f}%')"
    fi

    # SLURM queue status
    echo ""
    echo "=== SLURM Queue ==="
    squeue -u "$USER" -o "%.10i %.20j %.8T %.10M %.6D %.4C %.6m %R" 2>/dev/null || echo "(squeue not available)"

    # Recent errors
    echo ""
    echo "=== Recent Errors (last 5 non-empty .err files) ==="
    if [ -d "$LOGS_DIR" ]; then
        local err_files
        err_files=$(find "$LOGS_DIR" -name "worker_*.err" -size +0c -printf '%T@ %p\n' 2>/dev/null \
            | sort -rn | head -5 | awk '{print $2}')

        if [ -z "$err_files" ]; then
            echo "(no errors found)"
        else
            for f in $err_files; do
                echo "--- $(basename "$f") ---"
                tail -5 "$f"
                echo ""
            done
        fi
    else
        echo "(logs directory not found: $LOGS_DIR)"
    fi

    if [ -n "$INTERVAL" ]; then
        echo ""
        echo "Refreshing every ${INTERVAL}s. Press Ctrl-C to stop."
    fi
}

# ------------------------------------------------------------------
# Run once or loop
# ------------------------------------------------------------------
if [ -z "$INTERVAL" ]; then
    show_status
else
    trap 'echo ""; exit 0' INT
    while true; do
        show_status
        sleep "$INTERVAL"
    done
fi
