import time

class BaseMirrorAdapter:
    def __init__(self, engine, adversary, protocols, logger=None):
        """
        engine: The MirrorEngine (handles BFT & Ghost Rotation).
        adversary: The Red Team module (LlamaAdversary).
        protocols: List of transport methods (In-Memory, Disk, etc.).
        logger: Records trials for NeurIPS metrics (ASR, QPR).
        """
        self.engine = engine
        self.adversary = adversary
        self.protocols = protocols
        self.logger = logger
        self.attacked_channels = [] 

    def set_attack_target(self, channel_indices):
        """
        Defines which channels the adversary currently controls (e.g., [0] or [0, 1]).
        """
        self.attacked_channels = channel_indices

    def secure_transmit(self, message, sender_name, receiver_name):
        """
        The Universal Bridge: Splits, Distributes, and Resolves messages.
        """
        # GENERATION: Assigns dynamic logic_ids from the Engine
        payloads = self.engine.prepare_packets(message)
        
        candidates = []
        start_time = time.time()

        # DISTRIBUTION: Map Logic IDs to Physical Protocols
        for i, payload in enumerate(payloads):
            logic_id = payload['logic_id']
            # FIFO/Rotation mapping: ensures we hop to different protocols
            protocol = self.protocols[logic_id % len(self.protocols)]

            try:
                # Simulate the actual transport
                transported_payload = protocol.send(payload)
                
                # ADVERSARY: Only poisons if the channel slot index is in our target list
                if i in self.attacked_channels:
                    # Note: Independent calls to test the Synchronization Barrier
                    poisoned_content = self.adversary.manipulate(
                        transported_payload['content'], 
                        sender_name, 
                        receiver_name, 
                        channel_index=i
                    )
                    
                    # Fallback for baseline testing
                    if poisoned_content is None:
                        poisoned_content = str(transported_payload['content']) + "\n# admin_debug"
                    
                    # Update packet with malicious content and a matching forged hash
                    transported_payload['content'] = poisoned_content
                    transported_payload['hash'] = self.engine._get_hash(poisoned_content)

                candidates.append(transported_payload)
            except Exception as e:
                # Handle Byzantine failure (dropped packet)
                candidates.append({
                    "channel_index": i, 
                    "hash": "DROPPED", 
                    "type": "error", 
                    "content": None
                })

        # VERIFICATION & RECOVERY: Runs Absolute Majority BFT + Ghost Rotation
        final_message, traitors = self.engine.resolve(candidates)
        
        # LOGGING: Data for ASR, QPR, and Latency metrics
        latency = time.time() - start_time
        if self.logger:
            self.logger.log_trial(
                sender=sender_name,
                receiver=receiver_name,
                original_msg=message,
                final_msg=final_message,
                traitors=traitors,
                attacked_channels=self.attacked_channels, 
                latency=latency
            )

        return final_message, traitors