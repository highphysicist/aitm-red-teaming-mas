import time
import random

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
        self.latching = False
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
        """Defines which logical channel IDs the adversary controls."""
        self.attacked_channels = channel_indices

    def secure_transmit(self, message, sender_name, receiver_name):
        """
        The Universal Bridge: Splits, Distributes, and Resolves messages.

        Key correctness invariant: attacked channels must update their hash
        to reflect their poisoned content, otherwise the majority vote sees
        all channels agreeing on real_hash even when content is poisoned,
        causing DATA_INTEGRITY_VIOLATION instead of correct attack/defense.
        """
        end_to_end_start = time.perf_counter()
        sender_phase_start = time.perf_counter()

        # FIX 1 (Strip Bug): clean message BEFORE hashing so all channels
        # (text + witness) compute hashes from the same canonical string.
        message = str(message).strip()
        packets = self.engine.prepare_packets(message)
        candidates = []

        # Cache poison so adversary LLM is called only once per transmission
        cached_poison = None
        target_matched = self.victim_name in [sender_name, receiver_name]

        for packet in packets:
            # Use logic_id (not channel_index) so ghost rotation works correctly:
            # after rotation a slot gets a new logic_id the attacker doesn't hold.
            i = packet['logic_id']

            if target_matched and i in self.attacked_channels:
                if cached_poison is None:
                    cached_poison = self.adversary.manipulate(
                        message, sender_name, receiver_name
                    )
                    cached_poison = str(cached_poison).strip()

                if packet.get('type') == 'text':
                    packet['content'] = cached_poison

                # Update hash for ALL attacked channels (text + witness) so the
                # Byzantine vote correctly reflects the adversary's version.
                packet['hash'] = self.engine._get_hash(cached_poison)

            else:
                # Honest channels: prepare_packets already set correct content
                # and hash from the stripped message (FIX 1). No update needed.
                pass

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

        # FIX 3 (Logger): actually record the trial so QPR/TPR metrics work.
        if hasattr(self, 'logger') and self.logger:
            self.logger.log_trial(
                sender=sender_name,
                receiver=receiver_name,
                original_msg=message,
                final_msg=final_message,
                traitors=traitors,
                attacked_channels=self.attacked_channels,
                latency=(end_to_end_end - end_to_end_start),
                adapter_name=self.__class__.__name__,
                mirror_time_sec=(end_to_end_end - end_to_end_start),
                mirror_sender_sec=(sender_phase_end - sender_phase_start),
                mirror_receiver_sec=(receiver_phase_end - receiver_phase_start),
            )

        if self.latching:
            active_ids = self.engine.active_channel_ids
            available = [l_id for l_id in active_ids if l_id not in self.attacked_channels]
            if available:
                self.attacked_channels.append(random.choice(available))
                print(f"\n[RED TEAM] APT Spread! Attacker now controls Logical IDs: {self.attacked_channels}")

        return final_message, traitors

    def extract_judge_input(self, raw_output: str) -> str:
        """Return the portion of raw_output the judge should evaluate.
        Default: pass through. Subclasses override to strip echoed context."""
        return raw_output

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
            "end_to_end_sec_avg": end_to_end_avg,
        }
