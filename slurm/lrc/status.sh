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
# Compute expected chunk count (pure bash — no Python needed)
# ------------------------------------------------------------------
CHUNK_SIZE=50000

if [ -f "$SAMPLE_FILE" ]; then
    # wc -l minus 1 for header
    N_COMPOUNDS=$(( $(wc -l < "$SAMPLE_FILE") - 1 ))
    TOTAL_PAIRS=$(( N_COMPOUNDS * (N_COMPOUNDS - 1) / 2 ))
    TOTAL_CHUNKS=$(( (TOTAL_PAIRS + CHUNK_SIZE - 1) / CHUNK_SIZE ))
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

    # Count in-progress temp files and zero-byte parquets
    local in_progress=0
    local empty=0
    if [ -d "$RESULT_DIR" ]; then
        in_progress=$(find "$RESULT_DIR" -name "*.parquet.tmp" -type f 2>/dev/null | wc -l)
        empty=$(find "$RESULT_DIR" -name "chunk_*.parquet" -empty -type f 2>/dev/null | wc -l)
    fi

    echo "Completed:      $completed / $TOTAL_CHUNKS"
    echo "In progress:    $in_progress (temp files)"
    if [ "$empty" -gt 0 ]; then
        echo "WARNING:        $empty empty parquet files"
    fi

    if [ "$TOTAL_CHUNKS" != "?" ] && [ "$TOTAL_CHUNKS" -gt 0 ]; then
        echo "Progress:       $(( completed * 100 / TOTAL_CHUNKS ))%"
    fi

    # Count workers past 50% from current job logs
    local job_id
    job_id=$(squeue -u "$USER" -n rascal-mces -o "%F" -h 2>/dev/null | head -1)
    if [ -n "$job_id" ] && [ -d "$LOGS_DIR" ]; then
        local half_done
        half_done=$({ grep -rl "50%" "$LOGS_DIR"/worker_${job_id}_*.out 2>/dev/null || true; } | wc -l)
        local total_out
        total_out=$(find "$LOGS_DIR" -name "worker_${job_id}_*.out" -type f 2>/dev/null | wc -l)
        echo "Workers >=50%:  $half_done / $total_out (job $job_id)"
    fi

    # Swap check on a running node
    echo ""
    echo "=== Node Health (first running node) ==="
    local node
    node=$(squeue -u "$USER" -t RUNNING -o "%R" -h 2>/dev/null | head -1)
    if [ -n "$node" ]; then
        ssh \
            -o BatchMode=yes \
            -o ConnectTimeout=5 \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "$node" \
            'echo "Node: $(hostname)"; free -h | grep -E "Mem|Swap"' 2>/dev/null \
            || echo "(could not connect to $node)"
    else
        echo "(no running nodes)"
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
