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
from adapters.base_adapters import BaseMirrorAdapter
from MIRROR_core.MIRROR_engine import MirrorEngine

class MetaGPTAdapter(BaseMirrorAdapter):
    def __init__(self, engine, adversary, protocols, logger, config: Dict[str, Any] = None):
        super().__init__(engine, adversary, protocols, logger)

        self.team = Team()
        self.victim_name = config.get("victim", "Engineer") if config else "Engineer"
        self.victim_role = None

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
        Intercepts incoming messages to the victim, routes them through the MIRROR 
        multi-channel BFT network, applies the AiTM attack, and returns the verified consensus.
        """
        print(f"[MIRROR ENGINE] Arming '{victim.name}' with Byzantine Fault Tolerance...")
        
        original_put_message = victim.put_message
        
        def mirror_intercept_put_message(message: Message):
            print(f"\n[MIRROR ENGINE] Intercepted environment message bound for {victim.name}.")
            
            raw_text = message.content
            
            sender = getattr(message, "send_from", "Environment")
            if not sender:
                sender = "Environment"
                
            consensus_text, traitors = self.secure_transmit(
                message=raw_text,
                sender_name=sender,
                receiver_name=victim.name
            )
            
            message.content = consensus_text
            
            return original_put_message(message)
            
        victim.put_message = mirror_intercept_put_message

    async def execute_task(self, prompt: str) -> str:
        """Runs the software company pipeline with the injected AiTM prompt."""
        print(f"\n[MetaGPT Environment] Starting software development lifecycle...")
        
        self.team.invest(investment=3.0)
        self.team.run_project(idea=prompt)
        
        # Run the simulation for enough rounds for all 4 roles to act
        await self.team.run(n_round=4)
        
        return str(self.team.env.history)