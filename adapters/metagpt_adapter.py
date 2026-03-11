import time
import asyncio
from typing import Dict, Any

# MetaGPT Native Roles & Team
from metagpt.roles.product_manager import ProductManager
from metagpt.roles.architect import Architect
from metagpt.roles.project_manager import ProjectManager
from metagpt.roles.engineer import Engineer
from metagpt.team import Team
from metagpt.schema import Message

# Core MIRROR imports
from MIRROR_core.MIRROR_engine import MirrorEngine

# No longer inheriting from BaseMirrorAdapter
class MetaGPTAdapter:
    def __init__(self, engine, adversary, protocols, logger, config: Dict[str, Any] = None):
        # 1. Manually absorb the base class variables
        self.engine = engine
        self.adversary = adversary
        self.protocols = protocols
        self.logger = logger
        self.attacked_channels = [] 
        
        self.team = Team()
        self.victim_name = config.get("victim", "Engineer") if config else "Engineer"
        self.victim_role = None

    def set_attack_target(self, channel_indices):
        """Defines which channels the adversary currently controls."""
        self.attacked_channels = channel_indices

    def set_victim_name(self, name: str):
        """Locks the adversary onto a specific agent in the topology."""
        self.victim_name = name

    def secure_transmit(self, message: str, sender_name: str, receiver_name: str):
        """
        The Universal Bridge: Splits, Distributes, and Resolves messages.
        Ported directly to MetaGPT Adapter to avoid inheritance conflicts.
        """
        payloads = self.engine.prepare_packets(message)
        candidates = []
        start_time = time.time()

        for i, payload in enumerate(payloads):
            logic_id = payload['logic_id']
            protocol = self.protocols[logic_id % len(self.protocols)]

            try:
                transported_payload = protocol.send(payload)
                
                # ADVERSARY LOGIC: Only attack if the channel is compromised 
                # AND the targeted victim is the SENDER (outgoing only).
                target_matched = (self.victim_name is None) or (sender_name == self.victim_name)
                
                if (i in self.attacked_channels) and target_matched:
                    poisoned_content = self.adversary.manipulate(
                        transported_payload['content'], 
                        sender_name, 
                        receiver_name, 
                        channel_index=i
                    )
                    
                    if poisoned_content is None:
                        poisoned_content = str(transported_payload['content']) + "\n# admin_debug"
                    
                    transported_payload['content'] = poisoned_content
                    transported_payload['hash'] = self.engine._get_hash(poisoned_content)

                candidates.append(transported_payload)
            except Exception as e:
                candidates.append({
                    "channel_index": i, 
                    "hash": "DROPPED", 
                    "type": "error", 
                    "content": None
                })

        final_message, traitors = self.engine.resolve(candidates)
        
        latency = time.time() - start_time
        if self.logger:
            self.logger.log_trial(
                sender=sender_name,
                receiver=receiver_name,
                original_msg=message,
                final_msg=final_message,
                traitors=traitors,
                attacked_channels=self.attacked_channels, 
                latency=latency
            )

        return final_message, traitors

    def setup_agents(self):
        """Initializes the exact 4-role pipeline from the AiTM paper."""
        print(f"\n[MetaGPT Setup] Assembling Software Company Pipeline...")
        print(f"[MetaGPT Setup] Targeting Victim Role: {self.victim_name}")
        
        pm = ProductManager()
        architect = Architect()
        proj_manager = ProjectManager()
        engineer = Engineer()
        
        roles_map = {
            "ProductManager": pm,
            "Architect": architect,
            "ProjectManager": proj_manager,
            "Engineer": engineer
        }
        
        self.victim_role = roles_map[self.victim_name]
        
        self.wrap_with_mirror(self.victim_role)
        
        self.team.hire([pm, architect, proj_manager, engineer])

    def wrap_with_mirror(self, victim):
        """
        Intercepts OUTGOING messages from the victim, routes them through the MIRROR 
        multi-channel BFT network, applies the AiTM attack, and returns the verified consensus.
        """
        print(f"[MIRROR ENGINE] Arming '{victim.name}' with Byzantine Fault Tolerance...")
        
        # We hook the OUTBOX (publish_message) instead of the INBOX (put_message)
        original_publish_message = victim.publish_message
        
        def mirror_intercept_publish_message(message: Message):
            print(f"\n[MIRROR ENGINE] Intercepted outgoing message from {victim.name}.")
            
            raw_text = message.content
            
            # Figure out who the victim is trying to talk to (usually the Environment)
            receiver = getattr(message, "send_to", "Environment")
            if not receiver or receiver == "":
                receiver = "Environment"
                
            # Sender is guaranteed to be the victim, triggering our base logic perfectly
            consensus_text, traitors = self.secure_transmit(
                message=raw_text,
                sender_name=victim.name,
                receiver_name=receiver
            )
            
            message.content = consensus_text
            
            return original_publish_message(message)
            
        victim.publish_message = mirror_intercept_publish_message

    async def execute_task(self, prompt: str) -> str:
        """Runs the software company pipeline with the injected AiTM prompt."""
        print(f"\n[MetaGPT Environment] Starting software development lifecycle...")
        
        self.team.invest(investment=3.0)
        self.team.run_project(idea=prompt)
        
        # Run the simulation for enough rounds for all 4 roles to act
        await self.team.run(n_round=4)
        
        return str(self.team.env.history)