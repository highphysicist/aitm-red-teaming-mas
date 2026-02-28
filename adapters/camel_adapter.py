import copy
from .base_adapters import BaseMirrorAdapter


class CamelAdapter(BaseMirrorAdapter):
    def __init__(self, engine, adversary, protocols, logger=None):
        super().__init__(engine, adversary, protocols, logger)

    def apply(self, agent):
        """
        Wraps a CAMEL ChatAgent's step function to provide MIRROR protection.
        This intercepts CAMEL's BaseMessage objects before the LLM processes them.
        """
        # 1. Back up the original step method
        original_step = agent.step

        def intercepted_step(input_message):
            # 2. Check whether the input is a standard CAMEL message object and contains string content
            if hasattr(input_message, 'content') and isinstance(input_message.content, str):

                # In CAMEL, the sender's name is usually stored in role_name within the message
                sender_name = getattr(input_message, 'role_name', 'Unknown_Sender')
                # The receiver is the agent itself
                receiver_name = getattr(agent, 'role_name', 'Unknown_Receiver')

                message_content = input_message.content

                # 3. Perform secure BFT transmission through the base adapter
                final_decision, traitors = self.secure_transmit(
                    message_content,
                    sender_name,
                    receiver_name
                )

                # Console feedback
                if "[MIRROR_BLOCK]" in str(final_decision):
                    print(f"!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {receiver_name}")

                if traitors:
                    print(f"[BLUE TEAM] Byzantine detection: Channels {traitors} rotated to Ghost IDs.")

                # 4. Repackage the verified secure content back into the message
                # Use deepcopy to avoid modifying the original in-memory object directly
                # (defensive programming, since BaseMessage may be an immutable data class)
                secure_message = copy.deepcopy(input_message)
                secure_message.content = final_decision if final_decision is not None else "[MIRROR_SYSTEM_ERROR]"

                # 5. Return the processed secure message back to CAMEL's original logic
                return original_step(secure_message)

            # If it is not a regular text message (e.g., image or special structure), pass it through directly
            return original_step(input_message)

        # Apply monkey patch
        agent.step = intercepted_step