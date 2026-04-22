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

        # [FIX] Removed the broken self.logger.log() call here.

        packets = self.engine.prepare_packets(message)
        candidates = []
        traitors = []

        for packet in packets:
            i = packet['channel_index']
            if packet.get('type') == 'witness':
                candidates.append(packet)
                continue

            target_matched = self.victim_name in [sender_name, receiver_name]

            if target_matched and i in self.attacked_channels:
                poisoned_msg = self.adversary.manipulate(packet['content'], sender_name, receiver_name)
                packet['content'] = poisoned_msg

            candidates.append(packet)

        sender_phase_end = time.perf_counter()

        receiver_phase_start = time.perf_counter()
        final_message, traitors = self.engine.resolve(candidates)
        receiver_phase_end = time.perf_counter()

        end_to_end_end = time.perf_counter()

        # Telemetry updates
        self.telemetry["messages"] += 1
        self.telemetry["mirror_sender_sec_total"] += (sender_phase_end - sender_phase_start)
        self.telemetry["mirror_receiver_sec_total"] += (receiver_phase_end - receiver_phase_start)
        self.telemetry["mirror_time_sec_total"] += (end_to_end_end - end_to_end_start)
        self.telemetry["end_to_end_sec_total"] += (end_to_end_end - end_to_end_start)

        # TRUE DYNAMIC LATCHING SPREAD
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
        
        end_to_end_avg = (end_to_end_total / messages) if messages else 0.0

        return {
            "adapter": self.telemetry["adapter"],
            "messages": messages,
            "mirror_tokens": self.telemetry["mirror_tokens"],
            "mirror_time_sec_total": total_time,
            "mirror_time_sec_avg": avg_time,
            "mirror_sender_sec_total": sender_total,
            "mirror_receiver_sec_total": receiver_total,
            "end_to_end_sec_total": end_to_end_total,
            "end_to_end_sec_avg": end_to_end_avg  # [FIX] Added the missing key here!
        }