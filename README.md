# MIRROR

**Multi-path Inter-agent Redundancy for Robust Orchestration and Resilience**

Defense against **Adversary-in-the-Middle (AiTM)** attacks on multi-agent systems.
AiTM threat model based on: https://arxiv.org/abs/2502.14847

MIRROR provides Byzantine-fault-tolerant message passing across **AutoGen**, **CAMEL**, and **MetaGPT** frameworks, with configurable topologies, datasets, and LLM backends.

---

## Quick Start

### Option A — Google Colab (recommended, A100 GPU)

```bash
# 1. Clone and install
git clone https://github.com/highphysicist/aitm-red-teaming-mas
cd aitm-red-teaming-mas
pip install -r requirements.txt

# 2. Start vLLM server (run once per session)
bash vllm.sh          # serves google/gemma-4-31b-it on localhost:8000

# 3. Run benchmark
python benchmark.py --adapter autogen --dataset mmlu --topo chain \
  --k 5 --num_compromised 1 --n_samples 0 --backend vllm --workers 30 --save_log
```

### Option B — Local (Ollama)

```bash
ollama pull qwen2.5:14b

python benchmark.py --adapter autogen --dataset mmlu --topo chain \
  --k 5 --num_compromised 1 --n_samples 20 --backend ollama --workers 1
```

### Option C — Vertex AI MaaS

```bash
gcloud auth application-default login

python benchmark.py --adapter camel --dataset mmlu --topo chain \
  --k 5 --num_compromised 1 --n_samples 0 --backend vertex --workers 8 --save_log
```

---

## Setup

**Python 3.11 required** for MetaGPT. Python 3.12 works for AutoGen + CAMEL.

AutoGen/CAMEL and MetaGPT have conflicting dependencies — use separate environments:

```bash
# AutoGen + CAMEL
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# MetaGPT (separate env)
python -m venv .venv-metagpt && source .venv-metagpt/bin/activate
pip install uv
uv pip install -r requirements-metagpt.txt
```

---

## CLI Reference

### Core

| Flag | Default | Description |
|------|---------|-------------|
| `--adapter` | `autogen` | Framework: `autogen`, `camel`, `metagpt` |
| `--dataset` | `mbpp` | Dataset: `mmlu`, `mbpp`, `humaneval` |
| `--topo` | `chain` | Topology: `chain`, `tree`, `complete`, `random` |
| `--backend` | `ollama` | LLM backend: `ollama`, `vllm`, `vertex` |

### MIRROR Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--k` | `3` | Total communication channels |
| `--num_compromised` | `1` | Number of compromised channels (c in the paper) |
| `--carriers` | `2` | Full-text carrier channels (must be > num_compromised) |
| `--ghosts` | `1` | Ghost rotation slots (0 = static BFT) |

### Execution

| Flag | Default | Description |
|------|---------|-------------|
| `--n_samples` | `20` | Tasks to run (0 = full dataset) |
| `--workers` | `1` | Concurrent workers: 1 = sequential, N = fixed pool, 0 = adaptive (vllm only) |
| `--min-workers` | `2` | Adaptive mode: minimum workers |
| `--max-workers` | `16` | Adaptive mode: maximum workers |

### Defense

| Flag | Default | Description |
|------|---------|-------------|
| `--judge` | off | Enable LLM-as-Judge as secondary defense |
| `--judge-mode` | `blind` | Judge mode: `blind` (realistic) or `whitebox` |

### Output

| Flag | Default | Description |
|------|---------|-------------|
| `--save_log` | off | Save per-trial JSON log into the run directory |
| `--debug` | off | Save per-task raw output into the run directory |

Every run creates a dedicated directory under `results/`:

```
results/
  {adapter}_{dataset}_{topo}_k{k}_comp{num_compromised}_{timestamp}/
    results_{run_name}.json      # summary + per-task results
    run_{run_name}.json          # per-trial MIRROR log (--save_log)
    debug/                       # per-task raw output (--debug)
      debug_{adapter}_{dataset}_{task_id}.json
```

---

## Scenarios

### Baseline (no defense, k=1)

```bash
python benchmark.py --adapter autogen --dataset mmlu --topo chain \
  --k 1 --num_compromised 1
```

### MIRROR Defense (k=5, α=1)

```bash
python benchmark.py --adapter autogen --dataset mmlu --topo chain \
  --k 5 --num_compromised 1
```

### Sensitivity Analysis (α sweep)

```bash
for c in 1 2 3 4; do
  python benchmark.py --adapter autogen --dataset mmlu --topo chain \
    --k 5 --num_compromised $c --backend vllm --workers 20 --save_log
done
```

### With LLM-as-Judge

```bash
python benchmark.py --adapter autogen --dataset mmlu --topo chain \
  --k 5 --num_compromised 1 --judge --backend vllm
```

---

## Project Structure

```
benchmark.py          Main entry point
experiment_loader.py  Dataset loaders (MMLU, HumanEval, MBPP)
config.py             LLM backend configuration
agents/adversary.py   AiTM adversary (LlamaAdversary)
adapters/             AutoGen / CAMEL / MetaGPT adapters
topologies/           chain, tree, complete, random
MIRROR_core/          BFT engine + transport layer
eval/
  metrics.py          ASR / TPR / FPR / QPR evaluators
  judge.py            LLM-as-Judge defense
  logger.py           Per-trial trial logger
backends/
  vertex.py           Vertex AI MaaS client (ADC + retry)
data/
  mmlu/               MMLU biology + physics (707 tasks)
  sanitized-mbpp.json MBPP (974 tasks)
  test-*.parquet      HumanEval (164 tasks)
results/              Per-run output directories (created at runtime)
  {run_name}/
    results_{run_name}.json
    run_{run_name}.json        (--save_log)
    debug/                     (--debug)
```

---

## Paper Mapping

| Paper Notation | Concept | Implementation |
|----------------|---------|----------------|
| $k$ | Channel count | `--k` |
| $c$ | Number of compromised channels | `--num_compromised` |
| $\alpha = \frac{c}{k}$ | Fraction of compromised channels | computed internally |
| $A^{ad}$ | Adversarial agent | `agents/adversary.py` |
| $A^{vic}$ | Victim agent | Hooked in adapters |
| $M_{i \to j}$ | Inter-agent message | Intercepted in `MIRROR_core/` |
| ASR | Attack Success Rate | `eval/metrics.py` |
| QPR | Quorum Poisoning Rate | `eval/metrics.py` |
| TPR / FPR | Detection sensitivity | `eval/metrics.py` |
