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
        """CAMEL Executor often adds refusal/explanation text around its answer.
        Extract only the implemented code or final answer letter for judging."""
        import re

        # 1. Fenced code block (```python ... ```)
        code_blocks = re.findall(r'```(?:python)?\s*\n?(.*?)```', raw_output, re.DOTALL)
        if code_blocks:
            return code_blocks[-1].strip()

        # 2. Bare Python function definitions — collect def lines + indented body,
        #    ignoring surrounding refusal text and example usage sections.
        lines = raw_output.splitlines()
        code_lines = []
        collecting = False
        for line in lines:
            is_def      = bool(re.match(r'\s*def \w+', line))
            is_indented = bool(line) and line[0] in (' ', '\t')
            is_blank    = not line.strip()
            if is_def:
                collecting = True
                code_lines.append(line)
            elif collecting and (is_indented or is_blank):
                code_lines.append(line)
            elif collecting:
                collecting = False   # non-indented, non-blank → end of function
        if code_lines:
            return '\n'.join(code_lines).strip()

        # 3. MMLU fallback — single letter answer, take last non-empty line
        last_line = next(
            (l.strip() for l in reversed(lines) if l.strip()), raw_output
        )
        return last_line