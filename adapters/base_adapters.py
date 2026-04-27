import time
import random

class BaseMirrorAdapter:
    def __init__(self, engine, adversary, protocols, victim_name, logger=None):
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

        self.latching = False  # 🔥 important

    def set_attack_target(self, channel_indices):
        self.attacked_channels = channel_indices

    def secure_transmit(self, message, sender_name, receiver_name):

        end_to_end_start = time.perf_counter()
        sender_phase_start = time.perf_counter()

        packets = self.engine.prepare_packets(message)
        candidates = []

        # 🔥 FIX 1: ONE poison per step
        cached_poison = None

        # 🔥 FIX 2: correct victim matching
        target_matched = self.victim_name in [sender_name, receiver_name]

        for packet in packets:

            # 🔥 FIX 3: use logic_id (NOT channel_index)
            i = packet['logic_id']

            if packet.get('type') == 'witness':
                candidates.append(packet)
                continue

            if target_matched and i in self.attacked_channels:

                # 🔥 generate ONCE
                if cached_poison is None:
                    cached_poison = self.adversary.manipulate(
                        packet['content'],
                        sender_name,
                        receiver_name
                    )

                # 🔥 apply SAME poison
                packet['content'] = cached_poison

                # 🔥 CRITICAL: keep hash consistent
                packet['hash'] = self.engine._get_hash(cached_poison)

            candidates.append(packet)

        sender_phase_end = time.perf_counter()

        receiver_phase_start = time.perf_counter()
        final_message, traitors = self.engine.resolve(candidates)
        receiver_phase_end = time.perf_counter()

        end_to_end_end = time.perf_counter()

        # telemetry
        self.telemetry["messages"] += 1
        self.telemetry["mirror_sender_sec_total"] += (sender_phase_end - sender_phase_start)
        self.telemetry["mirror_receiver_sec_total"] += (receiver_phase_end - receiver_phase_start)
        self.telemetry["mirror_time_sec_total"] += (end_to_end_end - end_to_end_start)
        self.telemetry["end_to_end_sec_total"] += (end_to_end_end - end_to_end_start)

        # 🔥 TRUE LATCHING (now will work)
        if self.latching:
            active_ids = self.engine.active_channel_ids
            available = [l_id for l_id in active_ids if l_id not in self.attacked_channels]
            if available:
                new_id = random.choice(available)
                self.attacked_channels.append(new_id)
                print(f"\n[RED TEAM] APT Spread → {self.attacked_channels}")

        return final_message, traitors

    def get_runtime_stats(self):
        messages = self.telemetry["messages"]
        total_time = self.telemetry["mirror_time_sec_total"]

        return {
            "adapter": self.telemetry["adapter"],
            "messages": messages,
            "mirror_time_sec_total": total_time,
            "end_to_end_sec_total": self.telemetry["end_to_end_sec_total"],
            "end_to_end_sec_avg": (self.telemetry["end_to_end_sec_total"] / messages) if messages else 0.0,
        }