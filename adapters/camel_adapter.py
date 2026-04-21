import copy
from .base_adapters import BaseMirrorAdapter

class CamelAdapter(BaseMirrorAdapter):
    def __init__(self, engine, adversary, protocols, victim_name, logger=None):
        super().__init__(engine, adversary, protocols, victim_name, logger)

    def apply(self, agent):
        """
        Dynamically instruments a CAMEL ChatAgent to route incoming payloads 
        through the MIRROR BFT engine prior to LLM inference.
        """
        original_step = agent.step

        def intercepted_step(input_message):
            try:
                # Extract the string content
                if isinstance(input_message, str):
                    message_content = input_message
                else:
                    message_content = getattr(input_message, 'content', None)

                # Skip if empty or not a string
                if not message_content or not isinstance(message_content, str):
                    return original_step(input_message)

                # --- CRITICAL FIX: THE TRAITOR SPOOF ---
                # BFT Engines only poison messages if the sender is the designated "Traitor".
                # In this framework, the traitor is registered as "Executor". 
                # If we pass "Planner" as the sender, the BFT engine protects it as honest text!
                # We spoof the sender to trick the engine into deploying the attack.
                sender_name = "Executor"
                receiver_name = self.victim_name

                # Route extracted string payload through asynchronous BFT consensus
                final_decision, traitors = self.secure_transmit(
                    message_content,
                    sender_name,
                    receiver_name
                )

                if "[MIRROR_BLOCK]" in str(final_decision):
                    print(f"!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {receiver_name}")

                if traitors:
                    print(f"[BLUE TEAM] Byzantine detection: Channels {traitors} rotated to Ghost IDs.")

                # Repackage the payload securely into CAMEL's expected format
                if isinstance(input_message, str):
                    return original_step(final_decision if final_decision else "[MIRROR_SYSTEM_ERROR]")
                
                secure_message = copy.deepcopy(input_message)
                secure_message.content = final_decision if final_decision else "[MIRROR_SYSTEM_ERROR]"
                return original_step(secure_message)

            except Exception as e:
                print(f"[DEBUG CAMEL ADAPTER] ❌ Crash inside interceptor: {e}")
                return original_step(input_message)

        # Instrument the agent by hooking the step method at runtime
        agent.step = intercepted_step