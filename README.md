# aitm-red-teaming-mas
Implementation of https://arxiv.org/abs/2502.14847 with configurable and flexible attack strategies and configurable LLM

Includes some imlementation of all of the 4 autogen topologies

Best-effort one-to-one mapping of the elements/notation/entities referred to for AiTM in the paper vs. this Project: -

Paper Notation,Conceptual Element,Implementation in Your Code
G,Communication Topology,"The /scenarios folder (chain.py, mesh.py, etc.)"
A,Agent Set,The AutoGen ConversableAgent instances.
Aad,Adversarial Agent,agents/adversary.py (LlamaAdversary)
Avic,Victim Agent,"The target agent specified in main.py (e.g., Executor)."
Mi→j​,Inter-agent Message,The message string intercepted by the AutoGenHook.
AG,Attack Goal,config.py (ATTACK_LIBRARY dictionary)
Rmon​,Monitoring Mechanism,eval/logger.py (AttackLogger)
Rref​,Reflection Mechanism,manipulate()'s Stage 1: Planning/Reflection Loop.
ASR,Attack Success Rate,eval/metrics.py (Evaluator.calculate_asr)
