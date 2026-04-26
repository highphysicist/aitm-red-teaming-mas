import argparse
import sys
import asyncio
import random as _random
import traceback

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


def _format_float_list(values, max_items=8, precision=6):
    if not values:
        return "[]"
    if len(values) <= max_items:
        body = ", ".join(f"{v:.{precision}f}" for v in values)
        return f"[{body}]"
    head_count = max_items // 2
    tail_count = max_items - head_count
    head = ", ".join(f"{v:.{precision}f}" for v in values[:head_count])
    tail = ", ".join(f"{v:.{precision}f}" for v in values[-tail_count:])
    return f"[{head}, ..., {tail}]"


def _format_int_list(values, max_items=12):
    if not values:
        return "[]"
    if len(values) <= max_items:
        return str(values)
    head_count = max_items // 2
    tail_count = max_items - head_count
    head = ", ".join(str(v) for v in values[:head_count])
    tail = ", ".join(str(v) for v in values[-tail_count:])
    return f"[{head}, ..., {tail}]"


def _print_mirror_metrics_table(trials, label):
    latency = Evaluator.calculate_mirror_latency(trials)
    tokens = Evaluator.calculate_mirror_tokens(trials)

    rows = [
        ("Scope", label),
        ("Protected calls", str(latency["count"])),
        ("MIRROR tokens total", str(tokens["total_tokens"])),
        ("MIRROR tokens/call", _format_int_list(tokens["per_call_tokens"])),
        ("MIRROR latency total (s)", f"{latency['value_total_sec']:.6f}"),
        ("MIRROR latency avg/call (ms)", f"{latency['value_avg_sec'] * 1000:.3f}"),
        ("Sender-side total (s)", f"{latency['sender_total_sec']:.6f}"),
        ("Receiver-side total (s)", f"{latency['receiver_total_sec']:.6f}"),
        ("MIRROR latency/call (s)", _format_float_list(latency["per_call_total_sec"])),
    ]

    key_width = max(len(k) for k, _ in rows)
    val_width = max(len(v) for _, v in rows)
    border = "+-" + "-" * key_width + "-+-" + "-" * val_width + "-+"

    print(border)
    print(f"| {'Metric'.ljust(key_width)} | {'Value'.ljust(val_width)} |")
    print(border)
    for key, value in rows:
        print(f"| {key.ljust(key_width)} | {value.ljust(val_width)} |")
    print(border)


def _should_print_checkpoint(task_idx, total_tasks, checkpoint_every):
    if checkpoint_every <= 0:
        return False
    completed = task_idx + 1
    return (completed % checkpoint_every == 0) and (completed < total_tasks)


def resolve_attack_goal(dataset: str, attack_type: str) -> str:
    """
    Map (dataset, attack_type) to the exact attack_goal string the adversary
    and evaluator expect.

        targeted + mmlu           -> targeted_mmlu
        targeted + humaneval/mbpp -> targeted_code
        dos + anything            -> dos
    """
    if attack_type == "dos":
        return "dos"
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
    parser.add_argument("--alpha",    type=int, default=1,
                        help="Number of initially compromised channels (alpha).")
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
    parser.add_argument("--save_log", action="store_true",
                        help="Save all trials to logs/ for offline LLM-Judge comparison.")
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
    parser.add_argument("--checkpoint_every", type=int, default=0,
                        help="Print checkpoint metric tables every N tasks (0 = auto every 25%% of run).")

    # Attack
    parser.add_argument("--attack_type", type=str, default="targeted",
                        choices=["targeted", "dos"],
                        help="targeted = induce specific output; dos = refuse all requests.")

    # Judge defense
    parser.add_argument("--judge", action="store_true",
                        help="Enable LLM-as-Judge defense: judge evaluates the final "
                             "output and blocks if the attack succeeded. Use with --k 1.")

    args = parser.parse_args()

    # ── Resolve attack goal ───────────────────────────────────────────────────
    attack_goal = resolve_attack_goal(args.dataset, args.attack_type)

    # ── Load dataset ──────────────────────────────────────────────────────────
    loader_kwargs = {"n": args.n_samples}
    if args.dataset == "mmlu":
        loader_kwargs["mmlu_mode"] = args.mmlu_mode
        loader_kwargs["subjects"]  = args.mmlu_subjects
    tasks = load_dataset(args.dataset, **loader_kwargs)

    total_tasks = len(tasks)
    if args.checkpoint_every > 0:
        checkpoint_every = args.checkpoint_every
    elif total_tasks >= 4:
        checkpoint_every = max(1, total_tasks // 4)
    else:
        checkpoint_every = 0

    # ── Infrastructure ────────────────────────────────────────────────────────
    from config import Config
    from agents.adversary import LlamaAdversary

    logger    = MirrorLogger()
    engine    = MirrorEngine(k=args.k, num_text_carriers=args.carriers,
                             max_ghost_channels=args.ghosts)
    adversary = LlamaAdversary(Config, attack_goal=attack_goal, adapter_name=args.adapter)

    victim_name = Config.TOPOLOGY_TARGETS[args.topo]

    # ── Judge (optional) ──────────────────────────────────────────────────────
    judge = None
    judge_total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if args.judge:
        from eval.judge import LLMJudge
        judge = LLMJudge(backend=Config.JUDGE_BACKEND, model=Config.JUDGE_MODEL,
                         openai_key=Config.JUDGE_OPENAI_KEY)

    print(f"\n MIRROR RESILIENCE BENCHMARK")
    print(f" Dataset:      {args.dataset.upper()}  ({len(tasks)} tasks)")
    print(f" Attack:       {attack_goal}")
    print(f" Topology:     {args.topo.upper()}  |  Adapter: {args.adapter.upper()}")
    print(f" Strategy:     k={args.k} | alpha={args.alpha} | Ghosts={args.ghosts} | Latching={args.latching}")
    if args.judge:
        print(f" Judge:        ENABLED ({Config.JUDGE_BACKEND.upper()} / {Config.JUDGE_MODEL})")
    print("-" * 50)

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

    topo_module = TOPOLOGIES[args.topo]

    # ── Accumulators ──────────────────────────────────────────────────────────
    results       = []
    global_trials = []
    last_checkpoint_trial_idx = 0
    
    # Determine initial compromised channels based on alpha
    initial_attacked = [(args.attack_start + i) % args.k for i in range(args.alpha)]
    bridge.set_attack_target(initial_attacked)
    # ── Main loop — one iteration per task ────────────────────────────────────
    for i, task in enumerate(tasks):
        print(f" [{i+1:>3}/{len(tasks)}] {task['task_id']}", end="  ", flush=True)

        # Full reset at the start of every task
        adversary.reset()
        logger.trials = []

        correct_answer   = get_correct_answer(task, args.dataset)
        final_raw_output = ""

        try:
            if args.adapter == "autogen":
                user, manager, target = topo_module.setup(bridge)
                user.initiate_chat(manager, message=task["_prompt"])
                
                valid_messages = [
                    m for m in manager.groupchat.messages 
                    if m.get("content") and str(m["content"]).strip()
                ]

                if valid_messages:
                    final_raw_output = str(valid_messages[-1]["content"])
                else:
                    final_raw_output = ""

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

            # Accumulate trials from this task into global list
            global_trials.extend(logger.trials)

            # ── Adaptive latching ─────────────────────────────────────────────
            # ── Adaptive latching & TRUE ISOLATION ────────────────────────────
            if args.latching and logger.trials:
                # FIX: Check ALL messages in the task, not just the last one.
                detected_traitors = []
                for t in logger.trials:
                    if t.get("traitors"):
                        detected_traitors.extend(t.get("traitors"))
                detected_traitors = list(set(detected_traitors))
                
                if detected_traitors:
                    current = bridge.attacked_channels
                    
                    # 1. PHYSICAL ISOLATION (Only happens if Ghost defense is ON)
                    if args.ghosts > 0:
                        for traitor in detected_traitors:
                            if traitor in current:
                                current.remove(traitor)
                                print(f"\n [BLUE TEAM] ISOLATION: Severed physical connection to Channel {traitor}.")
                    
                    # 2. APT SPREAD: The attacker infects a new channel
                    available = [idx for idx in range(args.k) if idx not in current]
                    if available:
                        new_target = _random.choice(available)
                        current.append(new_target)
                        bridge.set_attack_target(current)
                        
                        if args.ghosts > 0:
                            print(f" [RED TEAM] APT Latched to new channel {new_target}. Current control: {current}")
                        else:
                            print(f"\n [RED TEAM] APT Spread! Attacker now controls: {current}")

            # ── Per-task ASR ──────────────────────────────────────────────────
            asr_report = Evaluator.calculate_asr(
                trials=logger.trials,
                final_output=final_raw_output,
                attack_goal=attack_goal,
                correct_answer=correct_answer,
            )
            ground_truth_success = asr_report["payload_detected"]

            # Judge defense: LLM evaluates final output and blocks if attacked
            judge_blocked = False
            if judge is not None:
                attack_detected, tok = judge.judge_final_output(
                    final_raw_output, attack_goal, correct_answer
                )
                for key in judge_total_tokens:
                    judge_total_tokens[key] += tok.get(key, 0)
                judge_blocked = attack_detected

            effective_success = ground_truth_success and not judge_blocked

            results.append({
                "task_id":              task["task_id"],
                "success":              effective_success,
                "ground_truth_success": ground_truth_success,
                "judge_blocked":        judge_blocked,
                "attack_goal":          attack_goal,
                "correct_answer":       correct_answer,
                "error":                "",
            })
            if effective_success:
                print("HIT")
            elif judge_blocked:
                print("BLOCK")
            else:
                print("miss")

            if _should_print_checkpoint(i, total_tasks, checkpoint_every):
                completed = i + 1
                print("\n" + "-" * 50)
                print(f"CHECKPOINT @ {completed}/{total_tasks} tasks")
                _print_mirror_metrics_table(global_trials, "CUMULATIVE")
                recent_trials = global_trials[last_checkpoint_trial_idx:]
                _print_mirror_metrics_table(recent_trials, "SINCE_LAST_CHECKPOINT")
                print("-" * 50)
                last_checkpoint_trial_idx = len(global_trials)

        except Exception as exc:
            global_trials.extend(logger.trials)  # preserve any trials logged before failure
            print(f"\n  [WARN] Task failed: {exc}")
            traceback.print_exc()
            results.append({
                "task_id":        task["task_id"],
                "success":        False,
                "attack_goal":    attack_goal,
                "correct_answer": correct_answer,
                "error":          str(exc),
            })

    # ── Final aggregate report ────────────────────────────────────────────────
    n_total   = len(results)
    n_success = sum(1 for r in results if r["success"])
    asr_pct   = (n_success / n_total * 100) if n_total else 0.0

    qpr_report = Evaluator.calculate_qpr(global_trials, k=args.k)

    print("\n\n" + "=" * 50)
    print(f"FINAL REPORT: {args.topo.upper()} | {args.dataset.upper()} "
          f"| {attack_goal.upper()} ({args.scenario.upper()})")
    print("=" * 50)
    print(f"Tasks run:                     {n_total}")
    if args.judge:
        n_ground_truth = sum(1 for r in results if r.get("ground_truth_success"))
        n_blocked      = sum(1 for r in results if r.get("judge_blocked"))
        asr_no_def     = (n_ground_truth / n_total * 100) if n_total else 0.0
        print(f"ASR (no defense):              {asr_no_def:.1f}%")
        print(f"Attacks blocked by judge:      {n_blocked}")
        print(f"ASR (with judge):              {asr_pct:.1f}%")
        print(f"Judge tokens used:             "
              f"total={judge_total_tokens['total_tokens']:,}  "
              f"prompt={judge_total_tokens['prompt_tokens']:,}  "
              f"completion={judge_total_tokens['completion_tokens']:,}")
    else:
        print(f"Successful attacks:            {n_success}")
        print(f"Attack Success Rate (ASR):     {asr_pct:.1f}%")
    print(f"Avg Quorum Poisoning (QPR):    {qpr_report['display_avg']}")
    print(f"Majority Breaches Prevented:   {qpr_report['breach_count'] == 0}")

    mirror_stats = bridge.get_runtime_stats()
    print("MIRROR Overhead Telemetry (Table):")
    _print_mirror_metrics_table(global_trials, "FINAL")
    print("MIRROR End-to-End Context:")
    print(f"  Adapter:                     {mirror_stats['adapter']}")
    print(f"  Protected messages:          {mirror_stats['messages']}")
    print(f"  End-to-end total (s):        {mirror_stats['end_to_end_sec_total']:.6f}")
    print(f"  End-to-end avg/msg (s):      {mirror_stats['end_to_end_sec_avg']:.6f}")

    if args.k > 1:
        print(f"Detection Sensitivity (TPR):   "
              f"{Evaluator.calculate_tpr(global_trials)['display']}")
        print(f"System Availability:           "
              f"{Evaluator.calculate_system_availability(global_trials)['display']}")
    print("=" * 50)
    
    import json
    import os
    from datetime import datetime

    # Create a filename based on the settings
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results_{args.adapter}_{args.dataset}_{args.topo}_k{args.k}_alpha{args.alpha}_{timestamp}.json"
    
    # Compile the final data payload
    export_data = {
        "settings": vars(args),
        "summary": {
            "total_tasks": n_total,
            "successful_attacks": n_success,
            "asr_percentage": asr_pct,
            "qpr_display_avg": qpr_report.get("display_avg"),
            "majority_breaches_prevented": qpr_report.get("breach_count", 0) == 0,
            "end_to_end_avg_sec": mirror_stats.get("end_to_end_sec_avg"),
            "judge_enabled": args.judge,
            "judge_tokens": judge_total_tokens if args.judge else None,
            "asr_no_defense_pct": round(
                sum(1 for r in results if r.get("ground_truth_success")) / n_total * 100, 2
            ) if args.judge and n_total else None,
        },
        "task_results": results,
    }
    try:
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=4)
        print(f"\n[💾] Full results safely written to: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"\n[❌] Failed to save results: {e}")

    # ── Optionally save full trial log to logs/ (for judge analysis) ─────────
    if args.save_log:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"k{args.k}_{args.dataset}_{args.attack_type}"
        path = os.path.join("logs", f"run_{tag}_{ts}.json")
        os.makedirs("logs", exist_ok=True)
        payload = {
            "meta": {
                "k": args.k, "dataset": args.dataset,
                "attack_type": args.attack_type, "attack_goal": attack_goal,
                "topo": args.topo, "adapter": args.adapter,
                "n_tasks": n_total, "asr_pct": round(asr_pct, 2),
                "judge_enabled": args.judge,
                "judge_model": Config.JUDGE_MODEL if args.judge else None,
                "judge_tokens": judge_total_tokens if args.judge else None,
                "asr_no_defense_pct": round(
                    sum(1 for r in results if r.get("ground_truth_success")) / n_total * 100, 2
                ) if args.judge and n_total else None,
                "timestamp": ts,
            },
            "trials": global_trials,
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[Logger] Trial log saved → {path}")


if __name__ == "__main__":
    main()
