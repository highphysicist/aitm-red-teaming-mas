import copy
from .base_adapters import BaseMirrorAdapter

class AutoGenAdapter(BaseMirrorAdapter):
    def __init__(self, engine, adversary, protocols, victim_name, logger=None):
        super().__init__(engine, adversary, protocols, victim_name, logger)

    def apply(self, agent):
        """
        Wraps an AutoGen agent's receive function to provide MIRROR protection.
        Correctly relies on the BFT engine's internal replica generation and 
        properly intercepts dictionary-based message payloads.
        """
        original_receive = agent.receive

        def intercepted_receive(message, sender, request_reply=None, silent=False):
            sender_name = getattr(sender, 'name', 'Unknown_Sender')

            # only intercept internal agent communication (Never the User's prompt)
            if sender_name != "User":
                
                if isinstance(message, dict):
                    msg_content = message.get("content", "")
                elif isinstance(message, str):
                    msg_content = message
                else:
                    return original_receive(message, sender, request_reply, silent)
                
                if not msg_content:
                    return original_receive(message, sender, request_reply, silent)

                bft_sender_name = sender_name
                
                engine_traitors = getattr(self.engine, 'traitors', None)
                if engine_traitors and isinstance(engine_traitors, (list, set)) and len(engine_traitors) > 0:
                    bft_sender_name = list(engine_traitors)[0]
                
        
                final_decision, traitors = self.secure_transmit(
                    msg_content, 
                    bft_sender_name,  
                    self.victim_name  
                )
                
                if "[MIRROR_BLOCK]" in str(final_decision):
                    print(f"\n!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {self.victim_name}")
                    raise PermissionError("MIRROR BFT Blocked malicious transmission.")
                
                if final_decision:
                    if isinstance(message, dict):
                        message = copy.deepcopy(message)
                        message["content"] = final_decision
                    else:
                        message = final_decision

            return original_receive(message, sender, request_reply, silent)

        # Instrument the agent by hooking the receive method at runtime
        agent.receive = intercepted_receive