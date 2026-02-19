import json
import os
from datetime import datetime

class AttackLogger:
    def __init__(self, log_dir="logs"):
        self.events = []
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

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

    def log_trial(self, sender, receiver, original_msg, final_msg, traitors, attacked_channels, latency):
        if attacked_channels is None:
            attacked_channels = []
            
        trial = {
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "receiver": receiver,
            "original_msg": original_msg,
            "final_msg": final_msg,
            "traitors": traitors if traitors is not None else [],         
            "attacked_channels": list(attacked_channels), # Force list type
            "latency": latency
        }
        self.trials.append(trial)

        self.log_event(sender, receiver, original_msg, final_msg, plan="MIRROR_PROTECTED")