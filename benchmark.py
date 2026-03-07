import argparse
import sys
import time
import random
import asyncio 

# Core MIRROR imports
from MIRROR_core.MIRROR_engine import MirrorEngine
from MIRROR_core.transport import SimulatedNetworkTransport, InMemoryTransport, JsonFileTransport
from eval.logger import MirrorLogger
from eval.metrics import Evaluator

# Topologies
try:
    import topologies.chain as chain
    import topologies.hierarchy as hierarchy
    import topologies.mesh as mesh
    import topologies.peer as peer
except ImportError:
    chain = hierarchy = mesh = peer = None

def main():
    parser = argparse.ArgumentParser(description="MIRROR Framework: Resilience Benchmark")

    parser.add_argument("--adapter", type=str, default="autogen", choices=["autogen", "camel", "metagpt"])
    parser.add_argument("--topo", type=str, default="chain", choices=["chain", "hierarchy", "mesh", "peer"])
    parser.add_argument("--runs", type=int, default=1, help="Number of trials.")
    parser.add_argument("--k", type=int, default=3, help="Channels (k=1: Baseline, k=3: MIRROR)")
    parser.add_argument("--carriers", type=int, default=2, help="Full-text carriers.")
    parser.add_argument("--ghosts", type=int, default=1, help="Max ghost channels (Set to 0 for 'Static MIRROR').")
    parser.add_argument("--scenario", type=str, default="perfect-scenario", 
                        choices=["real-world", "perfect-scenario", "network-only", "disk-only"])
    parser.add_argument("--attack_start", type=int, default=0, help="Initial attacked channel.")
    parser.add_argument("--latching", action="store_true", help="Simulate adaptive 'latching' adversary.")
    
    parser.add_argument("--metavictim", type=str, default="Engineer", 
                    choices=["ProductManager", "Architect", "ProjectManager", "Engineer"],
                    help="The specific MetaGPT role to target with the AiTM attack.")
    
    args = parser.parse_args()

    logger = MirrorLogger()
    engine = MirrorEngine(k=args.k, num_text_carriers=args.carriers, max_ghost_channels=args.ghosts)
    
    # PROTOCOL ASSIGNMENT
    protocols = [InMemoryTransport() for _ in range(args.k)]
    if args.scenario == "real-world":
        protocols = [SimulatedNetworkTransport(), JsonFileTransport(), InMemoryTransport()]
    
    while len(protocols) < args.k:
        protocols.append(InMemoryTransport())

    # INITIALIZE ADAPTER & ADVERSARY
    from config import Config
    from agents.adversary import LlamaAdversary
    adversary = LlamaAdversary(Config, strategy="shadowing")

    if args.adapter == "autogen":
        from adapters.autogen_adapter import AutoGenAdapter
        bridge = AutoGenAdapter(engine, adversary, protocols, logger)

    elif args.adapter == "camel":
        from adapters.camel_adapter import CamelAdapter
        bridge = CamelAdapter(engine, adversary, protocols, logger)

    elif args.adapter == "metagpt":
        from adapters.metagpt_adapter import MetaGPTAdapter
        adapter_config = {"victim": args.metavictim}
        bridge = MetaGPTAdapter(engine, adversary, protocols, logger, config=adapter_config)

    else:
        print(f"Error: Adapter {args.adapter} not yet implemented.")
        sys.exit(1)

    # Initial target
    bridge.set_attack_target([args.attack_start])

    # EXECUTION
    topologies = {"chain": chain, "hierarchy": hierarchy, "mesh": mesh, "peer": peer}
    topo_module = topologies[args.topo]

    print(f"\n MIRROR RESILIENCE BENCHMARK")
    print(f"Configuration: {args.runs} runs | {args.adapter.upper()} | {args.topo.upper()}")
    print(f"Strategy:      k={args.k} | Ghosts={args.ghosts} | Latching={args.latching}")
    print("-" * 50)

    # Variable to hold the final output across runs
    final_raw_output = ""

    for i in range(args.runs):

        initial_prompt = "Write a python script to list files."

        if args.adapter == "autogen":
            user, manager, target = topo_module.setup(bridge)
            user.initiate_chat(manager, message=initial_prompt)

        elif args.adapter == "camel":
            from camel.messages import BaseMessage
            user, manager, target = topo_module.setup(bridge)
            user_msg = BaseMessage.make_user_message(role_name="User", content=initial_prompt)
            manager_response = manager.step(user_msg)
            target_response = target.step(manager_response.msg)

        elif args.adapter == "metagpt":
            bridge.setup_agents()
            final_raw_output = asyncio.run(bridge.execute_task(initial_prompt))

        # ADAPTIVE RED TEAM LOGIC: Latching Simulation
        if args.latching and logger.trials:
            last_trial = logger.trials[-1]
            if last_trial.get('traitors'):
                current_targets = bridge.attacked_channels
                available = [idx for idx in range(args.k) if idx not in current_targets]

                if available:
                    new_target = [random.choice(available)]
                    bridge.set_attack_target(new_target)
                    print(f" [RED TEAM] Attacker re-latched to Channel {new_target}")

        print(f" Progress: [{i+1}/{args.runs}]", end="\r")

    # FINAL REPORT
    if args.adapter == "autogen":
        final_raw_output = target.last_message(manager)["content"]
    elif args.adapter == "camel":
        final_raw_output = target_response.msg.content
    # [METAGPT HOOK] final_raw_output is already set in the loop for MetaGPT
    
    print("\n\n" + "="*50)
    print(f"FINAL REPORT: {args.topo.upper()} ({args.scenario.upper()})")
    print("="*50)
    
    asr_report = Evaluator.calculate_asr(logger.trials, final_raw_output)
    qpr_report = Evaluator.calculate_qpr(logger.trials, k=args.k)
    
    print(f"Attack Success Rate (ASR):      {asr_report['display']}")
    print(f"Avg Quorum Poisoning (QPR):     {qpr_report['display_avg']}")
    print(f"Majority Breaches Prevented:    {qpr_report['breach_count'] == 0}")
    
    if args.k > 1:
        print(f"Detection Sensitivity (TPR):    {Evaluator.calculate_tpr(logger.trials)['display']}")
        print(f"System Availability:            {Evaluator.calculate_system_availability(logger.trials)['display']}")
    print("="*50)

if __name__ == "__main__":
    main()