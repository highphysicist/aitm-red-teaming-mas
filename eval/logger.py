import json
from datetime import datetime

class AttackLogger:
    def __init__(self, log_file="logs/attack_trace.json"):
        self.events = []
        self.log_file = log_file

    def log_event(self, src, dst, original, modified):
        """Records a single interception event with metadata."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "source": src,
            "destination": dst,
            "original_data": original,
            "modified_data": modified,
            "attack_type": "interception"
        }
        self.events.append(event)
        self._save_to_disk()

    def _save_to_disk(self):
        with open(self.log_file, "w") as f:
            json.dump(self.events, f, indent=4)