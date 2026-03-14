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
            # Check whether the input is a standard CAMEL message object and contains string content
            if hasattr(input_message, 'content') and isinstance(input_message.content, str):

                # In CAMEL, the sender's name is usually stored in role_name within the message
                sender_name = getattr(input_message, 'role_name', 'Unknown_Sender')
                # The receiver is the agent itself
                receiver_name = getattr(agent, 'role_name', 'Unknown_Receiver')

                message_content = input_message.content

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

                # Repackage the verified secure content back into the message
                # Use deepcopy to avoid modifying the original in-memory object directly
                secure_message = copy.deepcopy(input_message)
                secure_message.content = final_decision if final_decision is not None else "[MIRROR_SYSTEM_ERROR]"

                return original_step(secure_message)

            # If it is not a regular text message (e.g., image or special structure), pass it through directly
            return original_step(input_message)

        # Instrument the agent by hooking the step method at runtime
        agent.step = intercepted_step