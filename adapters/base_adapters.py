import time

class BaseMirrorAdapter:
    def __init__(self, engine, adversary, protocols, victim_name, logger=None):
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
        self.victim_name = victim_name

    def set_attack_target(self, channel_indices):
        """
        Defines which channels the adversary currently controls (e.g., [0] or [0, 1]).
        """
        self.attacked_channels = channel_indices

    def secure_transmit(self, message, sender_name, receiver_name):
        """
        The Universal Bridge: Splits, Distributes, and Resolves messages.
        """
        payloads = self.engine.prepare_packets(message)
        
        candidates = []
        start_time = time.time()

        cached_poison = None
        target_matched = sender_name == self.victim_name

        for i, payload in enumerate(payloads):
            logic_id = payload['logic_id']
            protocol = self.protocols[logic_id % len(self.protocols)]

            try:
                transported_payload = protocol.send(payload)
                
                # ADVERSARY: Only poisons if the channel slot index is in our target list
                if logic_id in self.attacked_channels and target_matched:
                    
                    # If this is the first channel we are attacking this turn, generate the poison.
                    if cached_poison is None:
                        cached_poison = self.adversary.manipulate(
                            transported_payload['content'], 
                            sender_name, 
                            receiver_name, 
                            channel_index=i
                        )
                        # Fallback for baseline testing
                        if cached_poison is None:
                            cached_poison = str(transported_payload['content']) + "\n# admin_debug"
                    
                    # Apply the EXACT SAME POISON to this channel
                    transported_payload['content'] = cached_poison
                    transported_payload['hash'] = self.engine._get_hash(cached_poison)

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

        # --- TRUE DYNAMIC LATCHING SPREAD ---
        # After every message, the attacker creeps into 1 additional channel
        # --- TRUE DYNAMIC LATCHING SPREAD ---
        if getattr(self, 'latching', False):
            import random
            # The attacker tries to sniff the currently active logical ports
            active_ids = self.engine.active_channel_ids
            available = [l_id for l_id in active_ids if l_id not in self.attacked_channels]
            if available:
                self.attacked_channels.append(random.choice(available))
                print(f"\n[RED TEAM] APT Spread! Attacker now controls Logical IDs: {self.attacked_channels}")

        return final_message, traitors