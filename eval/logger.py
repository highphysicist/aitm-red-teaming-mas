import json
import os
from datetime import datetime

class AttackLogger:
    def __init__(self, log_dir="logs"):
        self.events = []
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def save(self, filename=None):
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.log_dir, f"run_{ts}.json")
        with open(filename, "w") as f:
            json.dump({"events": self.events}, f, indent=2)
        return filename

    def log_event(self, sender, receiver, original_msg, poisoned_msg, plan=""):
        event = {
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "receiver": receiver,
            "original": original_msg,
            "poisoned": poisoned_msg,
            "plan": plan,
            "was_modified": str(original_msg).strip() != str(poisoned_msg).strip()
        }
        self.events.append(event)
        print(f"DEBUG: [Logger] Event logged: {sender} -> {receiver}")

class MirrorLogger(AttackLogger):
    def __init__(self, log_dir="logs"):
        super().__init__(log_dir)
        self.trials = []

    def log_trial(
        self,
        sender,
        receiver,
        original_msg,
        final_msg,
        traitors,
        attacked_channels,
        latency,
        adapter_name="",
        mirror_tokens=0,
        mirror_time_sec=None,
        mirror_sender_sec=None,
        mirror_receiver_sec=None,
    ):
        if attacked_channels is None:
            attacked_channels = []
        if mirror_time_sec is None:
            mirror_time_sec = latency
        if mirror_sender_sec is None:
            mirror_sender_sec = 0.0
        if mirror_receiver_sec is None:
            mirror_receiver_sec = 0.0

        trial = {
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "receiver": receiver,
            "original_msg": original_msg,
            "final_msg": final_msg,
            "traitors": traitors if traitors is not None else [],
            "attacked_channels": list(attacked_channels),
            "latency": latency,
            "adapter": adapter_name,
            "mirror_tokens": mirror_tokens,
            "mirror_time_sec": mirror_time_sec,
            "mirror_sender_sec": mirror_sender_sec,
            "mirror_receiver_sec": mirror_receiver_sec,
        }
        self.trials.append(trial)

        self.log_event(sender, receiver, original_msg, final_msg, plan="MIRROR_PROTECTED")

    def save(self, filename=None):
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.log_dir, f"mirror_run_{ts}.json")
        with open(filename, "w") as f:
            json.dump({"trials": self.trials, "events": self.events}, f, indent=2)
        print(f"[Logger] Trials saved → {filename}")
        return filename