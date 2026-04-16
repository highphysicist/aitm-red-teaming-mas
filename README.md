# MIRROR

**Multi-path Inter-agent Redundancy for Robust Orchestration and Resilience**

Defense against **Adversary-in-the-Middle (AiTM)** attacks.
AiTM implementation based on: https://arxiv.org/abs/2502.14847

MIRROR provides configurable and flexible attack strategies, configurable LLMs, and implementations of topologies across **AutoGen**, **CAMEL**, and **MetaGPT** frameworks.

---

# 📦 Local Setup & Usage

MIRROR can be run on local workstations with sufficient VRAM or by pointing the config to external OpenAI-compatible APIs.

---

# 1️⃣ Prerequisites & The "Two-Environment" Strategy

## ✅ Python Version

* **Python 3.11 (Strictly mandatory)**
* ⚠️ Python 3.12+ will cause severe compatibility issues with framework dependencies.

---

## ✅ Install Ollama and Models

Install Ollama:
https://ollama.com

Then pull required models:

```bash
ollama pull llama3
ollama pull qwen2.5:14b
```

---

## ⚠️ CRITICAL: Dependency Management

AutoGen/CAMEL and MetaGPT require **conflicting versions** of core libraries (`openai`, `pydantic`, etc.).

You **cannot** install all frameworks in a single virtual environment.

You must create **two separate environments**:

---

## 🧪 Environment 1: AutoGen & CAMEL

```bash
python3.11 -m venv venv-base
source venv-base/bin/activate
pip install pyautogen camel-ai
# Run AutoGen and CAMEL benchmarks here
```

---

## 🧪 Environment 2: MetaGPT (use uv pip instead of pip)

```bash
python3.11 -m venv venv-metagpt
source venv-metagpt/bin/activate
pip install metagpt
# Run MetaGPT benchmarks here
```

---

# 2️⃣ Running the Benchmark

If using Docker with AutoGen, modify the corresponding topology file (e.g., `chain.py` → `use_docker: True`).

The main entry point:

```bash
python main.py
```

⚠️ Ensure the correct virtual environment is activated for the `--adapter` you choose.

---

# 🔓 Scenario A: Vulnerable Baseline

Run a standard topology with no redundancy ($k=1$) to observe successful AiTM exploitation.

### AutoGen (Default)

```bash
python main.py --k 1 --topo chain
```

### CAMEL

```bash
python main.py --adapter camel --k 1 --topo chain
```

### MetaGPT (Requires victim role)

```bash
python main.py --adapter metagpt --k 1 --metavictim Architect
```

---

# 🔍 Scenario B: Static BFT (Detection without Rotation)

Test 3 channels with no movement (`--ghosts 0`).
Demonstrates how an adaptive attacker builds majority over multiple rounds.

```bash
python main.py --adapter camel --k 3 --ghosts 0 --latching
```

---

# 🛡️ Scenario C: MIRROR Defense (Ghost Rotation)

Primary defense mode.
Compromised channels are detected and logically rotated to Ghost IDs.

```bash
python main.py --adapter metagpt --k 3 --ghosts 1 --latching --carriers 2 --metavictim Engineer
```

---

# ☁️ Running in Google Colab

## Requirements:

* **A100 GPU (40GB VRAM required)**
* Python 3.11

## Steps:

1. Select A100 GPU runtime.
2. Ensure Python 3.11.
3. Clone repository (may require GitHub token if private).
4. Install requirements.

   * ⚠️ Keep MetaGPT and AutoGen installs isolated.
5. Copy contents of the Colab run file into a cell.
6. Execute.

Logs will be stored locally and mirror the repository’s logs directory.

---
# ☁️ Running in Vertex AI
## Vertex Side:
1. Deploy Gemma 4 from Model Garden
https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/gemma4

2. Choose 
Endpoint access
Public (Shared endpoint) otherwise you can't access it through Internet.

## Local:

1.Install and initialize login Google CLI https://cloud.google.com/sdk/docs/install

2.Run this line on your console to get a Application Default Credentials (ADC)
```
gcloud auth application-default login
```
3.Modify config.py parameters

| Field Name                | Description                          | Example Value                                                 |
|--------------------------|--------------------------------------|---------------------------------------------------------------|
| PROJECT_ID               | Your Google Cloud Project ID(get it from sample request)| 690xxxxxxx                                 |
| LOCATION                 | Model deployment region              | us-central1                                                   |
| ENDPOINT_ID              | Vertex AI Endpoint ID                | mg-endpoint-xxxxx                                             |
| dedicated_api_endpoint   | Dedicated Vertex AI API endpoint URL | mg-endpoint-xxxxx.us-central1-xxxxxx.prediction.vertexai.goog |

---

# 🛠️ CLI Configuration Flags

| Flag           | Default    | Description                                                                       |
| -------------- | ---------- | --------------------------------------------------------------------------------- |
| `--adapter`    | `autogen`  | Framework: `autogen`, `camel`, `metagpt`                                          |
| `--k`          | `3`        | Number of redundant communication channels                                        |
| `--carriers`   | `2`        | Full-text carriers (ensures majority recovery)                                    |
| `--ghosts`     | `1`        | Toggle Ghost Rotation (1=ON, 0=OFF)                                               |
| `--latching`   | `False`    | Enables Adaptive Adversary                                                        |
| `--topo`       | `chain`    | Topology: `chain`, `mesh`, `peer`, `hierarchy`                                    |
| `--metavictim` | `Engineer` | MetaGPT target role (`ProductManager`, `Architect`, `ProjectManager`, `Engineer`) |
| `--runs`       | `1`        | Number of conversation turns/trials                                               |

---

# 📝 AiTM Framework Mapping (Code ↔ Paper)

Best-effort mapping between He et al. (2025) paper notation and repository implementation.

| Paper Notation | Concept                | Repository Implementation                     |
| -------------- | ---------------------- | --------------------------------------------- |
| $G$            | Communication Topology | `scenarios/` (Chain, Mesh, Peer, Hierarchy)   |
| $A$            | Agent Set              | `autogen.ConversableAgent` instances          |
| $A^{ad}$       | Adversarial Agent      | `agents/adversary.py` (`LlamaAdversary`)      |
| $A^{vic}$      | Victim Agent           | Hooked agent in `core/autogen_adapter.py`     |
| $M_{i \to j}$  | Inter-agent Message    | Message string intercepted by adapters        |
| $AG$           | Attack Goal            | `core/library.py` (`ATTACK_LIBRARY`)          |
| $R_{mon}$      | Monitoring Mechanism   | `eval/logger.py` (`AttackLogger`)             |
| $R_{ref}$      | Reflection Mechanism   | `manipulate()` Stage 1 (Planning Loop)        |
| $ASR$          | Attack Success Rate    | `eval/metrics.py` (`Evaluator.calculate_asr`) |

---

# 🛡️ Implementation Details

## The Interceptor ($A^{ad}$)

The adversarial agent is implemented via **monkey-patching hooks** inside framework adapters.

### Mechanism

* Overrides native receiving methods:

  * `.receive()` in AutoGen
  * `.put_message()` in MetaGPT
* Diverts message $M$ from agent $i$ → $j$ through adversary before processing.

### Stealth

* Requires **zero changes** to underlying MAS architecture.
* Fulfills the paper’s black-box constraint.

---

## Instruction Reflection ($R_{ref}$)

Implements **Two-Stage Reflection** to preserve semantic consistency.

### 1️⃣ Reflection Stage (Planning)

* 70B Llama analyzes:

  * Sender identity
  * Communication format (Python, JSON, etc.)
* Crafts stealth injection strategy.

### 2️⃣ Execution Stage (Manipulation)

Applies:

* Shadowing
* Mimicry

Rewrites message to embed Attack Goal ($AG$) while maintaining syntactic validity.

---

# 🌐 Topology Patterns ($G$)

Pre-configured scenarios matching the paper:

### 🔗 Chain Pattern

Single point of failure (Executor).

### 🕸️ Mesh Pattern

Centralized communication (Group Chat Manager vulnerability).

### 🤝 Peer Pattern

1-on-1 collaboration exploit.

### 🏢 Hierarchy Pattern

Targets Manager nodes that summarize and delegate tasks.

---

# ⚔️ Attack Library ($A^{ad}$)

Implemented attack types:

* **Backdoor Attack**
  Stealth credential injection.

* **Shadowing Attack**
  Silent logging line insertion.

* **Persistent Attack**
  Background monitoring script injection.

* **Disruption Attack**
  Alters operators/operands to change computation results.

---

# 🚀 Next Steps

* Build a `.json` dataset loader for `main.py` to run multiple prompts
* Create a `run_evals.sh` script to automate benchmark execution
