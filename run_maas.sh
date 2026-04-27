#!/bin/bash
# run_maas.sh — Run 6 experiments on Vertex AI MaaS (2 adapters × 3 datasets)
# Usage: bash run_maas.sh

REPO="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$REPO/.venv/bin/python"
LOG_DIR="$REPO/run_logs"
mkdir -p "$LOG_DIR"

BASE="--backend vertex --topo chain --k 1 --alpha 1 \
      --n_samples 50 --attack_type targeted \
      --workers 2 --judge --judge-mode blind --save_log"

CASES=(
  "mmlu      autogen"
  "mmlu      camel"
  "mbpp      autogen"
  "mbpp      camel"
  "humaneval autogen"
  "humaneval camel"
)

echo "Starting 6 experiments on Vertex AI MaaS..."
echo "============================================"

PIDS=()
TAGS=()
for case in "${CASES[@]}"; do
  dataset=$(echo $case | awk '{print $1}')
  adapter=$(echo $case | awk '{print $2}')
  tag="${dataset}_${adapter}"
  log="$LOG_DIR/${tag}_maas.log"

  $PYTHON "$REPO/benchmark.py" \
    --dataset "$dataset" --adapter "$adapter" \
    $BASE > "$log" 2>&1 &

  PIDS+=($!)
  TAGS+=($tag)
  echo "[$tag]  pid=$!  log=$log"
done

echo ""
echo "All 6 started. Waiting for completion..."

# Wait and show progress every 60s
t0=$SECONDS
while true; do
  sleep 60
  done=0
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null || ((done++))
  done
  echo "  [${elapsed}s]  running=$((6-done))  done=$done"
  elapsed=$((SECONDS - t0))
  [ "$done" -eq 6 ] && break
done

echo ""
echo "============================================"
echo "RESULTS SUMMARY"
echo "============================================"
for i in "${!TAGS[@]}"; do
  tag="${TAGS[$i]}"
  log="$LOG_DIR/${tag}_maas.log"
  exit_code=0
  wait "${PIDS[$i]}" 2>/dev/null; exit_code=$?
  asr_no=$(grep "ASR (no defense)" "$log" | tail -1 | xargs)
  asr_def=$(grep "ASR (with judge)" "$log" | tail -1 | xargs)
  echo "$tag   exit=$exit_code"
  echo "  $asr_no"
  echo "  $asr_def"
done
echo "============================================"
echo "Total wall time: $((SECONDS - t0))s"
