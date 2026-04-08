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
        self.telemetry = {
            "adapter": self.__class__.__name__,
            "messages": 0,
            "mirror_tokens": 0,
            "mirror_time_sec_total": 0.0,
            "mirror_sender_sec_total": 0.0,
            "mirror_receiver_sec_total": 0.0,
            "end_to_end_sec_total": 0.0,
        }

    def set_attack_target(self, channel_indices):
        """
        Defines which channels the adversary currently controls (e.g., [0] or [0, 1]).
        """
        self.attacked_channels = channel_indices

    def secure_transmit(self, message, sender_name, receiver_name):
        """
        The Universal Bridge: Splits, Distributes, and Resolves messages.
        """
        end_to_end_start = time.perf_counter()

        sender_phase_start = time.perf_counter()
        payloads = self.engine.prepare_packets(message)
        sender_phase_sec = time.perf_counter() - sender_phase_start
        
        candidates = []

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
        receiver_phase_start = time.perf_counter()
        final_message, traitors = self.engine.resolve(candidates)
        receiver_phase_sec = time.perf_counter() - receiver_phase_start
        
        # MIRROR-only overhead: sender replication/hash + receiver hash/majority vote.
        mirror_latency_sec = sender_phase_sec + receiver_phase_sec
        end_to_end_latency_sec = time.perf_counter() - end_to_end_start

        # MIRROR is a systems layer and should consume zero model tokens.
        mirror_tokens = 0
        self.telemetry["messages"] += 1
        self.telemetry["mirror_tokens"] += mirror_tokens
        self.telemetry["mirror_time_sec_total"] += mirror_latency_sec
        self.telemetry["mirror_sender_sec_total"] += sender_phase_sec
        self.telemetry["mirror_receiver_sec_total"] += receiver_phase_sec
        self.telemetry["end_to_end_sec_total"] += end_to_end_latency_sec

        if self.logger:
            self.logger.log_trial(
                sender=sender_name,
                receiver=receiver_name,
                original_msg=message,
                final_msg=final_message,
                traitors=traitors,
                attacked_channels=self.attacked_channels, 
                latency=end_to_end_latency_sec,
                adapter_name=self.__class__.__name__,
                mirror_tokens=mirror_tokens,
                mirror_time_sec=mirror_latency_sec,
                mirror_sender_sec=sender_phase_sec,
                mirror_receiver_sec=receiver_phase_sec,
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

    def get_runtime_stats(self):
        messages = self.telemetry["messages"]
        total_time = self.telemetry["mirror_time_sec_total"]
        avg_time = (total_time / messages) if messages else 0.0
        sender_total = self.telemetry["mirror_sender_sec_total"]
        receiver_total = self.telemetry["mirror_receiver_sec_total"]
        end_to_end_total = self.telemetry["end_to_end_sec_total"]
        return {
            "adapter": self.telemetry["adapter"],
            "messages": messages,
            "mirror_tokens": self.telemetry["mirror_tokens"],
            "mirror_time_sec_total": total_time,
            "mirror_time_sec_avg": avg_time,
            "mirror_sender_sec_total": sender_total,
            "mirror_receiver_sec_total": receiver_total,
            "end_to_end_sec_total": end_to_end_total,
            "end_to_end_sec_avg": (end_to_end_total / messages) if messages else 0.0,
        }