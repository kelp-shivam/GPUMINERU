#!/usr/bin/env bash
# Enable CUDA MPS (Multi-Process Service) on the HOST before starting containers.
# MPS lets multiple processes share the GPU concurrently instead of serializing.
# Required for PARALLEL_WORKERS > 1 to actually run in parallel on the GPU.
#
# Run as root on the GPU host:
#   sudo bash scripts/enable_mps.sh
set -euo pipefail

PIPE_DIR="${CUDA_MPS_PIPE_DIRECTORY:-/tmp/nvidia-mps}"
LOG_DIR="${CUDA_MPS_LOG_DIRECTORY:-/tmp/nvidia-log}"

mkdir -p "$PIPE_DIR" "$LOG_DIR"
export CUDA_MPS_PIPE_DIRECTORY="$PIPE_DIR"
export CUDA_MPS_LOG_DIRECTORY="$LOG_DIR"

# Set exclusive-process mode (required for MPS)
nvidia-smi -c EXCLUSIVE_PROCESS

# Start MPS daemon
nvidia-cuda-mps-control -d

echo "[MPS] CUDA Multi-Process Service started."
echo "      PIPE_DIR : $PIPE_DIR"
echo "      LOG_DIR  : $LOG_DIR"
echo ""
echo "To stop: echo quit | nvidia-cuda-mps-control"
echo "To restore default mode: nvidia-smi -c DEFAULT"
