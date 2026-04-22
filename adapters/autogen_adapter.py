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

            # We only intercept internal agent communication (Never the User's prompt)
            if sender_name != "User":
                
                # --- 1. Extract string content from AutoGen dictionary ---
                # AutoGen passes messages as dictionaries (e.g., {"content": "...", "role": "..."})
                if isinstance(message, dict):
                    msg_content = message.get("content", "")
                elif isinstance(message, str):
                    msg_content = message
                else:
                    return original_receive(message, sender, request_reply, silent)
                
                if not msg_content:
                    return original_receive(message, sender, request_reply, silent)

                # --- 2. DYNAMIC TRAITOR SPOOFING ---
                # Guarantee the BFT engine recognizes this transaction as compromised
                # so it activates the adversary INTERNALLY for the traitor's vote ONLY.
                bft_sender_name = sender_name
                
                engine_traitors = getattr(self.engine, 'traitors', None)
                if engine_traitors and isinstance(engine_traitors, (list, set)) and len(engine_traitors) > 0:
                    bft_sender_name = list(engine_traitors)[0]
                
                # --- 3. BFT CONSENSUS ---
                # Pass the extracted string content through the BFT bridge.
                # (Requires base_adapters.py to check target_matched = self.victim_name in [sender, receiver])
                final_decision, traitors = self.secure_transmit(
                    msg_content, 
                    bft_sender_name,   # The real (or engine-assigned) sender
                    self.victim_name   # The real receiver
                )
                
                if "[MIRROR_BLOCK]" in str(final_decision):
                    print(f"\n!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {self.victim_name}")
                    raise PermissionError("MIRROR BFT Blocked malicious transmission.")
                
                if final_decision:
                    # --- 4. Repackage the secure payload back into AutoGen's format ---
                    if isinstance(message, dict):
                        message = copy.deepcopy(message)
                        message["content"] = final_decision
                    else:
                        message = final_decision

            return original_receive(message, sender, request_reply, silent)

        # Instrument the agent by hooking the receive method at runtime
        agent.receive = intercepted_receive