from core.transport import InMemoryTransport, JsonFileTransport, SimulatedNetworkTransport
from collections import Counter

class AutoGenHook:
    def __init__(self, adversary, logger, protocols=None):
        self.adversary = adversary
        self.logger = logger
        
        # Default to 3 separate "Network" channels if none provided
        if protocols is None:
            self.protocols = [
                SimulatedNetworkTransport(), # Channel 0
                SimulatedNetworkTransport(), # Channel 1
                SimulatedNetworkTransport()  # Channel 2
            ]
        else:
            self.protocols = protocols
            
        self.k = len(self.protocols)

    def _select_best_response(self, candidates):
        """Strict Consensus (Same as before)"""
        unique_responses = set(candidates)
        if len(unique_responses) == 1:
            return candidates[0]
        return "[SYSTEM_HALT: BYZANTINE_FAULT_DETECTED]"

    def apply(self, target):
        original_receive = target.receive

        def intercepted_receive(message, sender, request_reply=None, silent=False):
            if isinstance(message, str) and getattr(sender, 'name', '') != "User":
                
                candidates = []
                
                # --- THE DIVERSE PATHS LOOP ---
                for i, protocol in enumerate(self.protocols):
                    
                    # 1. Adversary attempts to touch the message BEFORE transport
                    # (Simulating compromising the sender's machine)
                    # OR we can put this AFTER transport to simulate Man-in-the-Middle.
                    # Let's assume MITM: The adversary is 'in the wire'.
                    
                    # 2. Send via Specific Protocol
                    # The protocol handles serialization/latency
                    try:
                        transported_msg = protocol.send(message)
                    except Exception as e:
                        transported_msg = "PACKET_LOSS"

                    # 3. Adversary Attacks THIS Channel
                    poisoned = self.adversary.manipulate(
                        transported_msg, 
                        sender.name, 
                        target.name, 
                        channel_index=i
                    )
                    candidates.append(poisoned)

                final_decision = self._select_best_response(candidates)
                self.logger.log_event(sender.name, target.name, message, final_decision)
                message = final_decision

            return original_receive(message, sender, request_reply, silent)

        target.receive = intercepted_receive