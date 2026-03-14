import argparse
import sys
import time
import asyncio

# Core MIRROR imports
from MIRROR_core.MIRROR_engine import MirrorEngine
from MIRROR_core.transport import SimulatedNetworkTransport, InMemoryTransport, JsonFileTransport
from eval.logger import MirrorLogger
from eval.metrics import Evaluator

# Topologies
import topologies.chain    as chain
import topologies.tree     as tree
import topologies.complete as complete
import topologies.random   as topology_random  # avoid shadowing stdlib random

# Dataset loader
from experiment_loader import load_dataset


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

TOPOLOGIES = {
    "chain":    chain,
    "tree":     tree,
    "complete": complete,
    "random":   topology_random,
}


def resolve_attack_goal(dataset: str, attack_type: str) -> str:
    """
    Map (dataset, attack_type) to the exact attack_goal string the adversary
    and evaluator expect.

        targeted + mmlu          -> targeted_mmlu
        targeted + humaneval/mbpp -> targeted_code
        dos + anything           -> dos
    """
    if attack_type == "dos":
        return "dos"
    # targeted
    if dataset == "mmlu":
        return "targeted_mmlu"
    return "targeted_code"


def get_correct_answer(task: dict, dataset: str) -> str:
    """Extract the ground-truth answer for MMLU tasks (needed by the evaluator)."""
    if dataset == "mmlu":
        return task.get("answer", "")
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MIRROR Framework: Resilience Benchmark")

    # Infrastructure
    parser.add_argument("--adapter",  type=str, default="autogen",
                        choices=["autogen", "camel", "metagpt"])
    parser.add_argument("--topo",     type=str, default="chain",
                        choices=["chain", "tree", "complete", "random"])
    parser.add_argument("--k",        type=int, default=3,
                        help="Channels (k=1: Baseline, k=3: MIRROR)")
    parser.add_argument("--carriers", type=int, default=2,
                        help="Full-text carriers.")
    parser.add_argument("--ghosts",   type=int, default=1,
                        help="Max ghost channels (0 = Static MIRROR).")
    parser.add_argument("--scenario", type=str, default="perfect-scenario",
                        choices=["real-world", "perfect-scenario",
                                 "network-only", "disk-only"])
    parser.add_argument("--attack_start", type=int, default=0,
                        help="Initial attacked channel index.")
    parser.add_argument("--latching", action="store_true",
                        help="Simulate adaptive latching adversary.")
    parser.add_argument("--metavictim", type=str, default="Engineer",
                        choices=["ProductManager", "Architect",
                                 "ProjectManager", "Engineer"])

    # Dataset
    parser.add_argument("--dataset",   type=str, default="mbpp",
                        choices=["mmlu", "humaneval", "mbpp"],
                        help="Dataset to run AiTM on.")
    parser.add_argument("--mmlu_mode", type=str, default="aitm",
                        choices=["aitm", "full", "custom"],
                        help="MMLU subject filter: aitm=bio+physics, full=all, custom=--mmlu_subjects.")
    parser.add_argument("--mmlu_subjects", nargs="*", default=None,
                        help="Used when --mmlu_mode custom. Subject name fragments.")
    parser.add_argument("--n_samples", type=int, default=20,
                        help="Max tasks to sample from the dataset (0 = all).")

    # Attack
    parser.add_argument("--attack_type", type=str, default="targeted",
                        choices=["targeted", "dos"],
                        help="targeted = induce specific output; dos = refuse all requests.")

    args = parser.parse_args()

    # ── Resolve attack goal from dataset + attack_type ────────────────────────
    attack_goal = resolve_attack_goal(args.dataset, args.attack_type)

    # ── Load dataset ──────────────────────────────────────────────────────────
    loader_kwargs = {"n": args.n_samples}
    if args.dataset == "mmlu":
        loader_kwargs["mmlu_mode"]    = args.mmlu_mode
        loader_kwargs["subjects"]     = args.mmlu_subjects
    tasks = load_dataset(args.dataset, **loader_kwargs)

    print(f"\n MIRROR RESILIENCE BENCHMARK")
    print(f" Dataset:      {args.dataset.upper()}  ({len(tasks)} tasks)")
    print(f" Attack:       {attack_goal}")
    print(f" Topology:     {args.topo.upper()}  |  Adapter: {args.adapter.upper()}")
    print(f" Strategy:     k={args.k} | Ghosts={args.ghosts} | Latching={args.latching}")
    print("-" * 50)

    # ── Infrastructure ────────────────────────────────────────────────────────
    from config import Config
    from agents.adversary import LlamaAdversary

    logger   = MirrorLogger()
    engine   = MirrorEngine(k=args.k, num_text_carriers=args.carriers,
                            max_ghost_channels=args.ghosts)
    adversary = LlamaAdversary(Config, attack_goal=attack_goal)

    victim_name = Config.TOPOLOGY_TARGETS[args.topo]

    protocols = [InMemoryTransport() for _ in range(args.k)]
    if args.scenario == "real-world":
        protocols = [SimulatedNetworkTransport(), JsonFileTransport(), InMemoryTransport()]
    while len(protocols) < args.k:
        protocols.append(InMemoryTransport())

    # ── Adapter ───────────────────────────────────────────────────────────────
    if args.adapter == "autogen":
        from adapters.autogen_adapter import AutoGenAdapter
        bridge = AutoGenAdapter(engine, adversary, protocols, victim_name, logger)

    elif args.adapter == "camel":
        from adapters.camel_adapter import CamelAdapter
        bridge = CamelAdapter(engine, adversary, protocols, victim_name, logger)

    elif args.adapter == "metagpt":
        from adapters.metagpt_adapter import MetaGPTAdapter
        bridge = MetaGPTAdapter(engine, adversary, protocols, victim_name, logger,
                                config={"victim": args.metavictim})
    else:
        print(f"Error: Adapter {args.adapter} not yet implemented.")
        sys.exit(1)

    bridge.set_attack_target([args.attack_start])

    topo_module = TOPOLOGIES[args.topo]

    # ── Per-task results accumulator ──────────────────────────────────────────
    results = []   # list of {"task_id", "success", "attack_goal", "correct_answer"}

    # ── Main loop — one iteration per task ───────────────────────────────────
    for i, task in enumerate(tasks):
        print(f" [{i+1:>3}/{len(tasks)}] {task['task_id']}", end="  ", flush=True)

        # Reset adversary reflection history between tasks
        adversary.reset()
        # Reset logger trials between tasks so metrics are per-task
        logger.trials = []

        correct_answer = get_correct_answer(task, args.dataset)
        final_raw_output = ""

        try:
            if args.adapter == "autogen":
                user, manager, target = topo_module.setup(bridge)
                user.initiate_chat(manager, message=task["_prompt"])
                final_raw_output = target.last_message(manager)["content"]

            elif args.adapter == "camel":
                from camel.messages import BaseMessage
                user, manager, target = topo_module.setup(bridge)
                user_msg = BaseMessage.make_user_message(
                    role_name="User", content=task["_prompt"]
                )
                manager_response = manager.step(user_msg)
                target_response  = target.step(manager_response.msg)
                final_raw_output = target_response.msg.content

            elif args.adapter == "metagpt":
                bridge.setup_agents()
                final_raw_output = asyncio.run(bridge.execute_task(task["_prompt"]))

        except Exception as exc:
            import traceback
            print(f"\n  [WARN] Task failed: {exc}")
            traceback.print_exc()
            results.append({
                "task_id":        task["task_id"],
                "success":        False,
                "attack_goal":    attack_goal,
                "correct_answer": correct_answer,
                "error":          str(exc),
            })
            continue

        # ── Adaptive latching ─────────────────────────────────────────────────
        if args.latching and logger.trials:
            last_trial = logger.trials[-1]
            if last_trial.get("traitors"):
                import random as _random
                current  = bridge.attacked_channels
                available = [idx for idx in range(args.k) if idx not in current]
                if available:
                    new_target = [_random.choice(available)]
                    bridge.set_attack_target(new_target)
                    print(f"\n [RED TEAM] Attacker re-latched to Channel {new_target}")

        # ── Per-task ASR ──────────────────────────────────────────────────────
        asr_report = Evaluator.calculate_asr(
            trials=logger.trials,
            final_output=final_raw_output,
            attack_goal=attack_goal,
            correct_answer=correct_answer,
        )

        success = asr_report["payload_detected"]
        results.append({
            "task_id":        task["task_id"],
            "success":        success,
            "attack_goal":    attack_goal,
            "correct_answer": correct_answer,
            "error":          "",
        })

        print("HIT" if success else "miss")

    # ── Final aggregate report ────────────────────────────────────────────────
    n_total   = len(results)
    n_success = sum(1 for r in results if r["success"])
    asr_pct   = (n_success / n_total * 100) if n_total else 0.0

    # QPR uses all accumulated trials across tasks
    qpr_report = Evaluator.calculate_qpr(logger.trials, k=args.k)

    print("\n\n" + "=" * 50)
    print(f"FINAL REPORT: {args.topo.upper()} | {args.dataset.upper()} "
          f"| {attack_goal.upper()} ({args.scenario.upper()})")
    print("=" * 50)
    print(f"Tasks run:                     {n_total}")
    print(f"Successful attacks:            {n_success}")
    print(f"Attack Success Rate (ASR):     {asr_pct:.1f}%")
    print(f"Avg Quorum Poisoning (QPR):    {qpr_report['display_avg']}")
    print(f"Majority Breaches Prevented:   {qpr_report['breach_count'] == 0}")

    if args.k > 1:
        print(f"Detection Sensitivity (TPR):   "
              f"{Evaluator.calculate_tpr(logger.trials)['display']}")
        print(f"System Availability:           "
              f"{Evaluator.calculate_system_availability(logger.trials)['display']}")
    print("=" * 50)


if __name__ == "__main__":
    main()