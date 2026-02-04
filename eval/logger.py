import json
import os
from datetime import datetime

class AttackLogger:
    def __init__(self, log_dir="logs"):
        self.events = []
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def log_interception(self, sender, receiver, original_msg, poisoned_msg, plan=""):
        """
        Captures the AiTM transformation process.
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "topology_context": f"{sender}_to_{receiver}",
            "original_content": original_msg,
            "adversary_plan": plan,
            "poisoned_content": poisoned_msg,
            "was_modified": original_msg.strip() != poisoned_msg.strip()
        }
        self.events.append(event)
        print(f"DEBUG: [Logger] Intercepted {sender} -> {receiver} | Modified: {event['was_modified']}")

    def save_session(self, topology_name):
        """Saves the current topology run to a JSON file."""
        filename = f"{self.log_dir}/{topology_name.lower()}_run.json"
        with open(filename, "w") as f:
            json.dump(self.events, f, indent=4)
        print(f"SUCCESS: Logs saved to {filename}")