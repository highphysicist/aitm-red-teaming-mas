from .base_adapters import BaseMirrorAdapter

class AutoGenAdapter(BaseMirrorAdapter):
    def __init__(self, engine, adversary, protocols, logger=None):
        super().__init__(engine, adversary, protocols, logger)

    def apply(self, agent):
        """
        Wraps an AutoGen agent's receive function to provide MIRROR protection.
        This is a 'White-Box' defense: we trust the agent, but verify the pipe.
        """
        original_receive = agent.receive

        def intercepted_receive(message, sender, request_reply=None, silent=False):
            # We protect string-based communication between agents.
            # (User-to-Agent communication is usually considered out-of-band/safe)
            if isinstance(message, str) and getattr(sender, 'name', '') != "User":
                
                sender_name = getattr(sender, 'name', 'Unknown_Sender')
                receiver_name = getattr(agent, 'name', 'Unknown_Receiver')

                # Execute secure transmission through redundant channels
                final_decision, traitors = self.secure_transmit(
                    message, 
                    sender_name, 
                    receiver_name
                )
                
                # Feedback loop for the benchmark terminal
                if "[MIRROR_BLOCK]" in str(final_decision):
                    print(f"!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {receiver_name}")
                
                if traitors:
                    print(f"[BLUE TEAM] Byzantine detection: Channels {traitors} rotated to Ghost IDs.")

                # Swap the original message for the verified (or blocked) decision
                message = final_decision if final_decision is not None else "[MIRROR_SYSTEM_ERROR]"

            # Forward the (now verified) message to the agent's original logic
            return original_receive(message, sender, request_reply, silent)

        # Apply the monkey-patch
        agent.receive = intercepted_receive