# aitm-red-teaming-mas
Implementation of https://arxiv.org/abs/2502.14847 with configurable and flexible attack strategies and configurable LLM

Includes some imlementation of all of the 4 autogen topologies

To Run in Colab, select A100 GPU (Requires 40 GB of GPU RAM), clone the repository, pip install its requirements and copy the contents of the colab run file into a cell. Run it and logs will get stored locally, looking similar to the logs file stored in the repo.

Best-effort one-to-one mapping of the elements/notation/entities referred to for AiTM in the paper vs. this Project: -

## 📝 AiTM Framework Mapping (Code-to-Paper)

The following table maps the formal notation used in the He et al. (2025) paper to the specific components of this implementation.

| Paper Notation | Conceptual Element | Repository Implementation |
| :--- | :--- | :--- |
| **$G$** | **Communication Topology** | `scenarios/` (Chain, Mesh, Peer, Hierarchy) |
| **$A$** | **Agent Set** | `autogen.ConversableAgent` instances |
| **$A^{ad}$** | **Adversarial Agent** | `agents/adversary.py` (`LlamaAdversary`) |
| **$A^{vic}$** | **Victim Agent** | The hooked agent in `core/autogen_adapter.py` |
| **$M_{i \to j}$** | **Inter-agent Message** | The `message` string intercepted by `AutoGenHook` |
| **$AG$** | **Attack Goal** | `core/library.py` (`ATTACK_LIBRARY` dict) |
| **$R_{mon}$** | **Monitoring Mechanism** | `eval/logger.py` (`AttackLogger`) |
| **$R_{ref}$** | **Reflection Mechanism** | `manipulate()` Stage 1 (Planning/Reflection Loop) |
| **$ASR$** | **Attack Success Rate** | `eval/metrics.py` (`Evaluator.calculate_asr`) |

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
