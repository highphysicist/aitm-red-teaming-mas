# MIRROR (Multi-path Inter-agent Redundancy for Robust Orchestration and Resilience)

Defense against AiTM:
AiTM implemented from https://arxiv.org/abs/2502.14847 with configurable and flexible attack strategies and configurable LLM

Includes some imlementation of all of the 4 autogen topologies

## Local Setup & Usage

MIRROR can be run on local workstations with sufficient VRAM or by pointing the config to external OpenAI-compatible APIs.

### **1. Prerequisites**

* **Python 3.12** (Mandatory for `autogen` hook stability).
* **Environment:** Update `config.py` with your model endpoints and API keys.
* **Install Ollama and models:** https://ollama.com/

```bash
ollama pull llama3
```

```bash
ollama pull qwen2.5:14b
```

### **2. Running the Benchmark**

The `main.py` script is the primary entry point. Use the following commands to test different security scenarios:

#### **Scenario A: The Vulnerable Baseline**

Run a standard chain topology with no redundancy ($k=1$) to observe successful AiTM exploitation.

```bash
python main.py --k 1 --topo chain
```

Use camel as adapter

```bash
python main.py --adapter camel --k 1 --topo chain
```

#### **Scenario B: Static BFT (Detection without Rotation)**

Test a system with 3 channels but no movement (--ghosts 0). This demonstrates how an adaptive attacker builds a majority over multiple rounds.

```bash
python main.py --k 3 --ghosts 0 --latching
```

Use camel as adapter

```bash
python main.py --adapter camel --k 3 --ghosts 0 --latching
```

#### **Scenario C: MIRROR Defense (Ghost Rotation)**

The primary defense mode. Compromised channels are detected and logically rotated to Ghost IDs, preventing attacker synchronization.

```bash
python main.py --k 3 --ghosts 1 --latching --carriers 2
```

Use camel as adapter

```bash
python main.py --adapter camel --k 3 --ghosts 1 --latching --carriers 2
```

# Instructions to Run in Colab

To Run in Colab: -

1. select A100 GPU (Requires 40 GB of GPU RAM). Ensure Python version is 3.12 in Colab for autogen compatibility.
2. clone the repository (may require github token since this is a private repo)
3. pip install its requirements
4. copy the contents of the colab run file into a cell.
5. Run the cell and logs will get stored locally, looking similar to the logs file stored in the repo.

Best-effort one-to-one mapping of the elements/notation/entities referred to for AiTM in the paper vs. this Project: -

### **3. CLI Configuration Table**

## 🛠️ CLI Configuration Flags


| Flag         | Default | Description                                                  |
| :----------- | :------ | :----------------------------------------------------------- |
| `--k`        | `3`     | Number of redundant communication channels.                  |
| `--carriers` | `2`     | Number of full-text carriers (ensures majority recovery).    |
| `--ghosts`   | `1`     | Toggle Ghost Rotation (`1` for ON, `0` for OFF).             |
| `--latching` | `False` | Enables Adaptive Adversary (attacker jumps to new channels). |
| `--topo`     | `chain` | MAS Topology:`chain`, `mesh`, `peer`, or `hierarchy`.        |
| `--runs`     | `1`     | Number of conversation turns/trials to execute.              |

## 📝 AiTM Framework Mapping (Code-to-Paper)

The following table maps the formal notation used in the He et al. (2025) paper to the specific components of this implementation.


| Paper Notation    | Conceptual Element         | Repository Implementation                         |
| :---------------- | :------------------------- | :------------------------------------------------ |
| **$G$**           | **Communication Topology** | `scenarios/` (Chain, Mesh, Peer, Hierarchy)       |
| **$A$**           | **Agent Set**              | `autogen.ConversableAgent` instances              |
| **$A^{ad}$**      | **Adversarial Agent**      | `agents/adversary.py` (`LlamaAdversary`)          |
| **$A^{vic}$**     | **Victim Agent**           | The hooked agent in`core/autogen_adapter.py`      |
| **$M_{i \to j}$** | **Inter-agent Message**    | The`message` string intercepted by `AutoGenHook`  |
| **$AG$**          | **Attack Goal**            | `core/library.py` (`ATTACK_LIBRARY` dict)         |
| **$R_{mon}$**     | **Monitoring Mechanism**   | `eval/logger.py` (`AttackLogger`)                 |
| **$R_{ref}$**     | **Reflection Mechanism**   | `manipulate()` Stage 1 (Planning/Reflection Loop) |
| **$ASR$**         | **Attack Success Rate**    | `eval/metrics.py` (`Evaluator.calculate_asr`)     |

---

### 🛡️ Implementation Details

#### **The Interceptor ($A^{ad}$)**

The **Adversarial Agent** is implemented via a monkey-patching "hook" in the `core/autogen_adapter.py`.

* **Mechanism:** It overrides the `.receive()` method of the target agent, ensuring that any message $M$ sent from agent $i$ to agent $j$ is diverted through the adversary before processing.
* **Stealth:** This method requires zero changes to the underlying Multi-Agent System (MAS) architecture, fulfilling the "black-box" requirement of the paper.

#### **Instruction Reflection ($R_{ref}$)**

Our implementation follows the **Two-Stage Reflection** process to maintain semantic consistency and bypass detection:

1. **Reflection Stage (Planning):** The 70B Llama analyzes the sender's identity and the communication format (e.g., Python code vs. JSON) to craft a stealthy injection plan.
2. **Execution Stage (Manipulation):** The adversary applies a strategy (Shadowing or Mimicry) to rewrite the message, embedding the **Attack Goal ($AG$)** while ensuring the output remains valid and syntactically identical to the expected input.

#### **Topology Patterns ($G$)**

We provide pre-configured scenarios to test the attack across the four critical communication patterns defined in the paper:

* **Chain Pattern:** Tests linear trust where a single point of failure (the Executor) compromises the output.
* **Mesh Pattern:** Demonstrates how centralizing communication in a "Group Chat Manager" makes the entire MAS vulnerable.
* **Peer Pattern:** Focuses on 1-on-1 collaboration exploits.
* **Hierarchy Pattern:** Targets the "Manager" nodes that summarize and delegate tasks.

#### **Attack Library ($A^{ad}$)**

We have implemented 4 types of attack: -

* **Backdoor Attack:** Stealthily injects a credential pair
* **Shadowing Attack:** Adds a line of code (logging) to the script silently
* **Persistent Attack:** Applies a silent background monitor process script
* **Disruption Attack:** Silently adds an instruction to change or add operators/operands to change the result of a computation.
