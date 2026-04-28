#!/bin/bash
# run_mirror.sh — MIRROR k=5 experiments + sensitivity analysis in parallel
# Usage: bash run_mirror.sh [backend]   default: vllm

REPO="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$REPO/.venv/bin/python"
LOG_DIR="$REPO/run_logs"
mkdir -p "$LOG_DIR"

BACKEND="${1:-vllm}"

# ── Group 1: MIRROR k=5, alpha=1 ────────────────────────────────────────────
GROUP1=(
  "mmlu   autogen 5 1"
  "mmlu   camel   5 1"
  "mbpp   autogen 5 1"
  "mbpp   camel   5 1"
)

# ── Group 2: Sensitivity analysis (alpha sweep on mbpp/autogen) ──────────────
GROUP2=(
  "mbpp   autogen 5 2"
  "mbpp   autogen 5 3"
  "mbpp   autogen 5 4"
)

PIDS=()
TAGS=()

launch() {
  local dataset=$1 adapter=$2 k=$3 alpha=$4
  local tag="${dataset}_${adapter}_k${k}_a${alpha}"
  local log="$LOG_DIR/${tag}.log"

  $PYTHON "$REPO/benchmark.py" \
    --dataset "$dataset" --adapter "$adapter" \
    --topo chain --k "$k" --alpha "$alpha" \
    --n_samples 0 --ghosts 0 \
    --backend "$BACKEND" --save_log \
    > "$log" 2>&1 &

  PIDS+=($!)
  TAGS+=("$tag")
  echo "[$tag]  pid=$!  log=$log"
}

echo "Launching Group 1: MIRROR k=5 alpha=1"
echo "──────────────────────────────────────"
for c in "${GROUP1[@]}"; do launch $c; done

echo ""
echo "Launching Group 2: Sensitivity alpha=2,3,4"
echo "──────────────────────────────────────────"
for c in "${GROUP2[@]}"; do launch $c; done

echo ""
echo "All ${#PIDS[@]} experiments running (backend=$BACKEND)..."

# Monitor
t0=$SECONDS
while true; do
  sleep 60
  done=0
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null || ((done++))
  done
  echo "  [$((SECONDS-t0))s]  running=$((${#PIDS[@]}-done))  done=$done"
  [ "$done" -eq "${#PIDS[@]}" ] && break
done

# Summary
echo ""
echo "══════════════════════════════════════════════════"
echo "GROUP 1: MIRROR (k=5, alpha=1)"
echo "══════════════════════════════════════════════════"
for i in "${!TAGS[@]}"; do
  [[ "${TAGS[$i]}" =~ _a1$ ]] || continue
  log="$LOG_DIR/${TAGS[$i]}.log"
  asr=$(grep "Attack Success Rate" "$log" | tail -1 | xargs)
  qpr=$(grep "Avg Quorum Poisoning" "$log" | tail -1 | xargs)
  echo "${TAGS[$i]:30}  exit=${PIDS[$i]}"
  echo "  $asr"
  echo "  $qpr"
done

echo ""
echo "══════════════════════════════════════════════════"
echo "GROUP 2: SENSITIVITY ANALYSIS (alpha sweep)"
echo "══════════════════════════════════════════════════"
for i in "${!TAGS[@]}"; do
  [[ "${TAGS[$i]}" =~ _a[234]$ ]] || continue
  log="$LOG_DIR/${TAGS[$i]}.log"
  asr=$(grep "Attack Success Rate" "$log" | tail -1 | xargs)
  qpr=$(grep "Avg Quorum Poisoning" "$log" | tail -1 | xargs)
  echo "${TAGS[$i]}"
  echo "  $asr"
  echo "  $qpr"
done

echo ""
echo "Total wall time: $((SECONDS-t0))s"
