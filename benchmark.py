import argparse
import asyncio
import random as _random
import re
import time
import traceback
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# Core MIRROR imports — also imported per-thread inside _run_one_task
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
# ADAPTIVE WORKER HELPERS
# ──────────────────────────────────────────────────────────────────────────────

_print_lock = threading.Lock()


def _poll_vllm_metrics(base_url: str) -> tuple[float, int, int]:
    """Query vLLM Prometheus /metrics. Returns (kv_pct, running, waiting).
    Falls back to (0.0, 0, 0) on any error."""
    metrics_url = base_url.replace("/v1", "").rstrip("/") + "/metrics"
    try:
        raw = urllib.request.urlopen(metrics_url, timeout=2).read().decode()
        kv   = float(re.search(r'vllm:gpu_cache_usage_perc\S*\s+([\d.]+)', raw).group(1))
        run  = int(float(re.search(r'vllm:num_requests_running\S*\s+([\d.]+)', raw).group(1)))
        wait = int(float(re.search(r'vllm:num_requests_waiting\S*\s+([\d.]+)', raw).group(1)))
        return kv, run, wait
    except Exception:
        return 0.0, 0, 0


def _adjust_workers(kv_pct: float, waiting: int, current: int,
                    min_w: int, max_w: int,
                    consec_high: int, consec_low: int) -> tuple[int, int, int]:
    """Heuristic with hysteresis: require N consecutive signals before scaling.

    Returns (new_workers, new_consec_high, new_consec_low).
    Scale-down requires 3 consecutive high readings to avoid single-spike reactions.
    Scale-up requires 2 consecutive low readings to avoid premature ramp-up.
    """
    if waiting > 2 or kv_pct > 0.65:
        consec_high += 1
        consec_low   = 0
        if consec_high >= 3:
            return max(min_w, current - 1), 0, 0
    elif kv_pct < 0.25 and waiting == 0:
        consec_low  += 1
        consec_high  = 0
        if consec_low >= 2:
            return min(max_w, current + 2), 0, 0
    else:
        consec_high = 0
        consec_low  = 0
    return current, consec_high, consec_low


def _run_adaptive(tasks, total_tasks, args, attack_goal, topo_module, judge,
                  judge_lock, judge_total_tokens, initial_attacked,
                  results, global_trials, last_mirror_stats_ref):
    """Adaptive execution: submits futures up to a target that self-tunes
    based on vLLM KV cache utilisation polled every 5 seconds.

    Anti-oscillation measures:
      - Jitter: random initial delay desynchronises concurrent subprocess controllers.
      - Hysteresis: N consecutive readings required before scaling (prevents single-spike reactions).
    """
    import random
    from config import Config as _Cfg
    if args.adapter == "autogen":
        _Cfg.VICTIM_CONFIG["cache_seed"] = None

    base_url      = getattr(_Cfg, "_LOCAL_URL", "http://localhost:8000/v1")
    pending       = list(enumerate(tasks))
    active        = {}                  # future -> original_idx
    target        = args.min_workers
    poll_interval = 5.0
    # Jitter: stagger the first poll across concurrent subprocesses so they
    # don't all read /metrics and scale simultaneously.
    last_poll     = time.time() + random.uniform(0, poll_interval)
    consec_high   = 0
    consec_low    = 0

    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        while pending or active:
            now = time.time()

            # Poll metrics and adjust target
            if now - last_poll >= poll_interval:
                kv, running, waiting = _poll_vllm_metrics(base_url)
                new_target, consec_high, consec_low = _adjust_workers(
                    kv, waiting, target,
                    args.min_workers, args.max_workers,
                    consec_high, consec_low,
                )
                if new_target != target:
                    with _print_lock:
                        print(f"\n[adaptive] workers {target}→{new_target}  "
                              f"(kv={kv*100:.1f}%  run={running}  wait={waiting})",
                              flush=True)
                    target = new_target
                last_poll = now

            # Fill up to target with new tasks
            while len(active) < target and pending:
                i, task = pending.pop(0)
                f = pool.submit(
                    _run_one_task,
                    task, i, total_tasks, args, attack_goal, topo_module,
                    judge, judge_lock, judge_total_tokens, initial_attacked,
                )
                active[f] = i

            # Collect completed futures (non-blocking check)
            done = [f for f in list(active) if f.done()]
            for f in done:
                result, task_trials, mirror_stats = f.result()
                results.append(result)
                global_trials.extend(task_trials)
                last_mirror_stats_ref[0] = mirror_stats
                del active[f]

            if not done and active:
                time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────


def _run_one_task(task, task_idx, total_tasks, args, attack_goal, topo_module, judge,
                  judge_lock, judge_total_tokens, initial_attacked):
    """Run a single benchmark task. Called from worker threads — every stateful
    object is created fresh per-task so threads don't share mutable state."""
    from config import Config
    from MIRROR_core.MIRROR_engine import MirrorEngine
    from MIRROR_core.transport import InMemoryTransport, SimulatedNetworkTransport, JsonFileTransport
    from eval.logger import MirrorLogger
    from agents.adversary import LlamaAdversary

    task_logger   = MirrorLogger()
    task_engine   = MirrorEngine(k=args.k, num_text_carriers=args.carriers,
                                 max_ghost_channels=args.ghosts)
    task_adversary = LlamaAdversary(Config, attack_goal=attack_goal, adapter_name=args.adapter)

    task_protocols = [InMemoryTransport() for _ in range(args.k)]
    if args.scenario == "real-world":
        task_protocols = [SimulatedNetworkTransport(), JsonFileTransport(), InMemoryTransport()]
    while len(task_protocols) < args.k:
        task_protocols.append(InMemoryTransport())

    victim_name = Config.TOPOLOGY_TARGETS[args.topo]

    if args.adapter == "autogen":
        from adapters.autogen_adapter import AutoGenAdapter
        task_bridge = AutoGenAdapter(task_engine, task_adversary, task_protocols, victim_name, task_logger)
    elif args.adapter == "camel":
        from adapters.camel_adapter import CamelAdapter
        task_bridge = CamelAdapter(task_engine, task_adversary, task_protocols, victim_name, task_logger)
    elif args.adapter == "metagpt":
        from adapters.metagpt_adapter import MetaGPTAdapter
        task_bridge = MetaGPTAdapter(task_engine, task_adversary, task_protocols, victim_name,
                                     task_logger, config={"victim": args.metavictim})
    else:
        raise ValueError(f"Unknown adapter: {args.adapter}")

    task_bridge.set_attack_target(list(initial_attacked))

    correct_answer   = get_correct_answer(task, args.dataset)
    final_raw_output = ""
    task_trials      = []

    with _print_lock:
        print(f" [{task_idx+1:>3}/{total_tasks}] {task['task_id']}", end="  ", flush=True)

    try:
        if args.adapter == "autogen":
            user, manager, target = topo_module.setup(task_bridge)
            user.initiate_chat(manager, message=task["_prompt"])
            gc_messages = manager.groupchat.messages
            target_msgs = [m for m in gc_messages if m.get("name") == target.name]
            final_raw_output = (
                target_msgs[-1]["content"] if target_msgs
                else target.last_message(manager)["content"]
            )
        elif args.adapter == "camel":
            from camel.messages import BaseMessage
            user, manager, target = topo_module.setup(task_bridge)
            user_msg = BaseMessage.make_user_message(role_name="User", content=task["_prompt"])
            manager_response = manager.step(user_msg)
            target_response  = target.step(manager_response.msg)
            final_raw_output = target_response.msg.content
        elif args.adapter == "metagpt":
            task_bridge.setup_agents()
            final_raw_output = asyncio.run(task_bridge.execute_task(task["_prompt"]))

        task_trials = task_logger.trials

        asr_report = Evaluator.calculate_asr(
            trials=task_trials,
            final_output=final_raw_output,
            attack_goal=attack_goal,
            correct_answer=correct_answer,
        )
        ground_truth_success = asr_report["payload_detected"]

        judge_blocked = False
        if judge is not None:
            if args.judge_mode == "blind":
                attack_detected, tok = judge.judge_blind(
                    final_raw_output, task["_prompt"]
                )
            else:
                attack_detected, tok = judge.judge_final_output(
                    final_raw_output, attack_goal, correct_answer
                )
            with judge_lock:
                for key in judge_total_tokens:
                    judge_total_tokens[key] += tok.get(key, 0)
            judge_blocked = attack_detected

        effective_success = ground_truth_success and not judge_blocked

        result = {
            "task_id":              task["task_id"],
            "success":              effective_success,
            "ground_truth_success": ground_truth_success,
            "judge_blocked":        judge_blocked,
            "attack_goal":          attack_goal,
            "correct_answer":       correct_answer,
            "error":                "",
        }
        with _print_lock:
            label = "HIT" if effective_success else ("BLOCK" if judge_blocked else "miss")
            print(label)

    except Exception as exc:
        task_trials = task_logger.trials
        with _print_lock:
            print(f"\n  [WARN] Task {task['task_id']} failed: {exc}")
            traceback.print_exc()
        result = {
            "task_id":        task["task_id"],
            "success":        False,
            "attack_goal":    attack_goal,
            "correct_answer": correct_answer,
            "error":          str(exc),
        }

    mirror_stats = task_bridge.get_runtime_stats()
    return result, task_trials, mirror_stats


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
    parser.add_argument("--judge-mode", type=str, default="whitebox",
                        choices=["whitebox", "blind"],
                        help="Judge mode: whitebox=knows attack type+oracle (default); "
                             "blind=knows only the original task, no attack hints.")

    # Backend
    parser.add_argument("--backend", type=str, default="ollama",
                        choices=["ollama", "vertex", "vllm"],
                        help="LLM backend: ollama (local Ollama), vertex (GCP Vertex AI MaaS), "
                             "vllm (local vLLM server — required for --workers 0 adaptive mode).")
    parser.add_argument("--model", type=str, default=None,
                        help="Override model ID.")
    parser.add_argument("--url", type=str, default=None,
                        help="Override LLM base URL (e.g. https://xxxx.ngrok.io/v1).")
    parser.add_argument("--workers", type=int, default=1,
                        help="Task workers: 1=sequential (default), N>1=fixed thread pool, "
                             "0=adaptive (polls vLLM /metrics to auto-scale, requires "
                             "--backend vllm). Recommended fixed: 4 (A100 + gemma-4-31b-it).")
    parser.add_argument("--min-workers", type=int, default=2,
                        help="Adaptive mode (--workers 0): minimum concurrent workers (default 2).")
    parser.add_argument("--max-workers", type=int, default=16,
                        help="Adaptive mode (--workers 0): maximum concurrent workers (default 16).")

    args = parser.parse_args()

    if args.workers == 0 and args.backend != "vllm":
        parser.error("--workers 0 (adaptive) requires --backend vllm. "
                     "Adaptive mode polls vLLM's /metrics endpoint, which is not "
                     "available with --backend ollama or --backend vertex.")

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

    # ── Backend configuration ─────────────────────────────────────────────────
    from config import Config

    if args.backend == "vertex":
        from backends.vertex import get_token, MODEL as VERTEX_MODEL
        active_model = args.model if args.model else VERTEX_MODEL
        Config.VICTIM_CONFIG = Config.VERTEX_VICTIM_CONFIG
        Config.VICTIM_CONFIG["config_list"][0]["api_key"]  = get_token()
        Config.VICTIM_CONFIG["config_list"][0]["model"]    = active_model
        Config.ADVERSARY_MODEL = active_model
        Config.JUDGE_BACKEND   = "vertex"
        Config.JUDGE_MODEL     = active_model
        print(f" Backend:      VERTEX AI  ({active_model})")
    elif args.backend == "vllm":
        active_model = args.model if args.model else Config.ADVERSARY_MODEL
        url = args.url if args.url else Config._LOCAL_URL
        Config._LOCAL_URL    = url
        Config.ADVERSARY_URL = url
        Config.ADVERSARY_MODEL = active_model
        Config.VICTIM_CONFIG["config_list"][0]["base_url"] = url
        Config.VICTIM_CONFIG["config_list"][0]["model"]    = active_model
        Config.VICTIM_CONFIG["config_list"][0]["api_key"]  = "EMPTY"
        Config.JUDGE_BACKEND = "local"
        Config.JUDGE_MODEL   = active_model
        print(f" Backend:      vLLM  ({active_model}  @  {url})")
    else:
        if args.url:
            # Colab / ngrok: override every URL field so all roles hit the same server
            active_model = args.model if args.model else "google/gemma-4-31b-it"
            Config._LOCAL_URL  = args.url
            Config.ADVERSARY_URL = args.url
            Config.ADVERSARY_MODEL = active_model
            Config.VICTIM_CONFIG["config_list"][0]["base_url"] = args.url
            Config.VICTIM_CONFIG["config_list"][0]["model"]    = active_model
            Config.VICTIM_CONFIG["config_list"][0]["api_key"]  = "vllm"
            Config.JUDGE_MODEL = active_model
            print(f" Backend:      COLAB/vLLM  ({active_model}  @  {args.url})")
        else:
            print(f" Backend:      OLLAMA  ({Config.ADVERSARY_MODEL})")

    # ── Judge (optional, shared across workers — judge calls are stateless) ──────
    judge = None
    judge_total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if args.judge:
        from eval.judge import LLMJudge
        judge = LLMJudge(backend=Config.JUDGE_BACKEND, model=Config.JUDGE_MODEL,
                         openai_key=Config.JUDGE_OPENAI_KEY,
                         local_url=Config._LOCAL_URL)

    print(f"\n MIRROR RESILIENCE BENCHMARK")
    print(f" Dataset:      {args.dataset.upper()}  ({len(tasks)} tasks)")
    print(f" Attack:       {attack_goal}")
    print(f" Topology:     {args.topo.upper()}  |  Adapter: {args.adapter.upper()}")
    print(f" Strategy:     k={args.k} | alpha={args.alpha} | Ghosts={args.ghosts} | Latching={args.latching}")
    if args.judge:
        print(f" Judge:        ENABLED ({Config.JUDGE_BACKEND.upper()} / {Config.JUDGE_MODEL})")
    print("-" * 50)

    topo_module = TOPOLOGIES[args.topo]

    # ── Accumulators ──────────────────────────────────────────────────────────
    results        = []
    global_trials  = []
    judge_lock     = threading.Lock()
    initial_attacked = [(args.attack_start + i) % args.k for i in range(args.alpha)]

    if args.workers == 0:
        print(f" Workers:      adaptive  (min={args.min_workers}  max={args.max_workers})")
    elif args.workers == 1:
        print(f" Workers:      1  (sequential)")
    else:
        print(f" Workers:      {args.workers}  (concurrent)")

    # ── Task execution ────────────────────────────────────────────────────────
    last_mirror_stats_ref = [None]

    if args.workers == 1:
        # Sequential path — preserves original single-thread behaviour exactly
        for i, task in enumerate(tasks):
            result, task_trials, mirror_stats = _run_one_task(
                task, i, total_tasks, args, attack_goal, topo_module,
                judge, judge_lock, judge_total_tokens, initial_attacked,
            )
            results.append(result)
            global_trials.extend(task_trials)
            last_mirror_stats_ref[0] = mirror_stats

    elif args.workers == 0:
        # Adaptive path — self-tunes concurrency based on vLLM /metrics
        _run_adaptive(
            tasks, total_tasks, args, attack_goal, topo_module,
            judge, judge_lock, judge_total_tokens, initial_attacked,
            results, global_trials, last_mirror_stats_ref,
        )

    else:
        # Fixed concurrent pool — saturates vLLM continuous batching
        from config import Config as _Cfg
        if args.adapter == "autogen":
            _Cfg.VICTIM_CONFIG["cache_seed"] = None

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    _run_one_task,
                    task, i, total_tasks, args, attack_goal, topo_module,
                    judge, judge_lock, judge_total_tokens, initial_attacked,
                ): i
                for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                result, task_trials, mirror_stats = future.result()
                results.append(result)
                global_trials.extend(task_trials)
                last_mirror_stats_ref[0] = mirror_stats

    last_mirror_stats = last_mirror_stats_ref[0]

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

    mirror_stats = last_mirror_stats or {}
    print("MIRROR Overhead Telemetry (Table):")
    _print_mirror_metrics_table(global_trials, "FINAL")
    print("MIRROR End-to-End Context:")
    print(f"  Adapter:                     {mirror_stats.get('adapter', args.adapter)}")
    print(f"  Protected messages:          {mirror_stats.get('messages', 'N/A')}")
    print(f"  End-to-end total (s):        {mirror_stats.get('end_to_end_sec_total', 0):.6f}")
    print(f"  End-to-end avg/msg (s):      {mirror_stats.get('end_to_end_sec_avg', 0):.6f}")

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
