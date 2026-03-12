#!/bin/bash
# Transfer sample data to LRC (run locally on workstation).
#
# Usage:
#   bash slurm/lrc/transfer_data.sh <SAMPLE_NAME>
#
# This rsyncs the sample TSV to the LRC scratch filesystem
# via the dedicated transfer node (lrc-xfer.lbl.gov).

set -euo pipefail

LRC_USER="${LRC_USER:-lucacappelletti}"
LRC_XFER="lrc-xfer.lbl.gov"
REMOTE_DATA="/global/scratch/users/${LRC_USER}/rascal-mces-data"

SAMPLE_NAME="${1:-}"
if [ -z "$SAMPLE_NAME" ]; then
    echo "Usage: bash slurm/lrc/transfer_data.sh <SAMPLE_NAME>"
    echo ""
    echo "Example:"
    echo "  bash slurm/lrc/transfer_data.sh massspecgym"
    exit 1
fi

LOCAL_FILE="data/samples/${SAMPLE_NAME}.tsv"
if [ ! -f "$LOCAL_FILE" ]; then
    echo "ERROR: Local sample file not found: $LOCAL_FILE"
    echo "Run 'uv run rascal-mces sample --name $SAMPLE_NAME --all' first."
    exit 1
fi

echo "Transferring $LOCAL_FILE to LRC..."
echo "  Remote: ${LRC_USER}@${LRC_XFER}:${REMOTE_DATA}/samples/"

rsync -avP \
    "$LOCAL_FILE" \
    "${LRC_USER}@${LRC_XFER}:${REMOTE_DATA}/samples/"

echo ""
echo "Transfer complete. On LRC, verify with:"
echo "  wc -l /global/scratch/users/${LRC_USER}/rascal-mces-data/samples/${SAMPLE_NAME}.tsv"
