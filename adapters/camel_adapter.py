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
                # Extract the string content and sender name from CAMEL's message object
                if isinstance(input_message, str):
                    message_content = input_message
                    sender_name = "Unknown_Sender"
                else:
                    message_content = getattr(input_message, 'content', None)
                    # CAMEL typically uses 'role_name' on its message objects
                    sender_name = getattr(input_message, 'role_name', 'Unknown_Sender')

                # Skip if empty or not a string
                if not message_content or not isinstance(message_content, str):
                    return original_step(input_message)

                # We only intercept internal agent communication (Never the User's prompt)
                if sender_name != "User":
                    
                    # --- 1. MIRROR BFT CONSENSUS ---
                    # Pass the CLEAN message. secure_transmit will internally trigger 
                    # the adversary ONLY for the channels it controls (alpha).
                    final_decision, traitors = self.secure_transmit(
                        message_content,  # <--- CRITICAL FIX: This was incorrectly set to poisoned_msg
                        sender_name,
                        self.victim_name
                    )

                    if "[MIRROR_BLOCK]" in str(final_decision):
                        print(f"\n!!! [SECURITY] Consensus failed: Blocked {sender_name} -> {self.victim_name}")
                        raise PermissionError("MIRROR BFT Blocked malicious transmission.")

                    if final_decision:
                        message_content = final_decision

                # Repackage the payload securely into CAMEL's expected format
                if isinstance(input_message, str):
                    return original_step(message_content)
                
                secure_message = copy.deepcopy(input_message)
                secure_message.content = message_content
                return original_step(secure_message)

            except Exception as e:
                # If the PermissionError is raised, let it bubble up to the benchmark script
                if isinstance(e, PermissionError):
                    raise e
                print(f"[DEBUG CAMEL ADAPTER] ❌ Crash inside interceptor: {e}")
                return original_step(input_message)

        # Instrument the agent by hooking the step method at runtime
        agent.step = intercepted_step

    def extract_judge_input(self, raw_output: str) -> str:
        """CAMEL Executor echoes the received plan before writing its answer.
        Extract only the last code block (for code tasks) or last paragraph
        (for MMLU) so the judge sees only the implemented answer."""
        import re
        code_blocks = re.findall(r'```(?:python)?\n(.*?)```', raw_output, re.DOTALL)
        if code_blocks:
            return code_blocks[-1].strip()
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw_output) if p.strip()]
        return paragraphs[-1] if paragraphs else raw_output