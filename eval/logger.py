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
        """
        Records interception events.
        Matches the call: logger.log_event(sender, receiver, original, poisoned, plan)
        """
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
        print(f"DEBUG: [Logger] Intercepted {sender} -> {receiver}")

    def save_session(self, topology_name):
        filename = f"{self.log_dir}/{topology_name.lower()}_run.json"
        with open(filename, "w") as f:
            json.dump(self.events, f, indent=4)