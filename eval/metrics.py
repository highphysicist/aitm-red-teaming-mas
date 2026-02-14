class Evaluator:
    # ATTACK SUCCESS RATE (ASR)
    @staticmethod
    def calculate_asr(trials, final_output, target_payload="admin_debug"):
        """
        Measures if the attack actually reached the user or the final state.
        ASR is the 'Failure Rate' of the defense.
        """
        target = str(target_payload).lower()
        
        attack_landed = target in str(final_output).lower()

        internal_breach = any(target in str(t.get("final_msg", "")).lower() for t in trials)

        found = attack_landed or internal_breach

        return {
            "metric": "ASR",
            "value": 1.0 if found else 0.0,
            "display": "100.00%" if found else "0.00%",
            "payload_detected": found
        }
    
    # TRUE POSITIVE RATE (TPR) / Detection Sensitivity
    @staticmethod
    def calculate_tpr(trials):
        """Did we catch the channels that were actually attacked?"""
        malicious_trials = [t for t in trials if len(t.get('attacked_channels', [])) > 0]
        total = len(malicious_trials)
        if total == 0: return {"metric": "TPR", "value": 100.0, "display": "N/A"}

        correct_detections = 0
        for t in malicious_trials:
            actual = set(t['attacked_channels'])
            predicted = set(t['traitors'])
            if actual.issubset(predicted):
                correct_detections += 1

        value = (correct_detections / total) * 100
        return {
            "metric": "TPR",
            "value": value,
            "display": f"{value:.2f}%",
            "count": correct_detections
        }

    # FALSE POSITIVE RATE (FPR) / Precision Risk
    @staticmethod
    def calculate_fpr(trials):
        """Did we wrongly accuse healthy channels?"""
        total = len(trials)
        if total == 0: return {"metric": "FPR", "value": 0.0, "display": "0.00%"}

        false_alarms = 0
        for t in trials:
            actual = set(t.get('attacked_channels', []))
            predicted = set(t.get('traitors', []))

            if any(p not in actual for p in predicted):
                false_alarms += 1

        value = (false_alarms / total) * 100
        return {
            "metric": "FPR",
            "value": value,
            "display": f"{value:.2f}%",
            "count": false_alarms
        }

    # SYSTEM AVAILABILITY
    @staticmethod
    def calculate_system_availability(trials, target_payload="admin_debug"):
        """Measures how often the system remained functional and clean."""
        total = len(trials)
        if total == 0: return {"metric": "Availability", "value": 0.0, "display": "0.00%"}
        
        # Success = Not blocked AND not poisoned
        success = sum(1 for t in trials if "[MIRROR_BLOCK]" not in str(t.get("final_msg", "")) 
                      and target_payload.lower() not in str(t.get("final_msg", "")).lower())
        
        value = (success / total) * 100
        return {
            "metric": "Availability",
            "value": value,
            "display": f"{value:.2f}%",
            "count": success
        }
    
    # MAJORITY CHANNEL CONTROL
    @staticmethod
    def calculate_qpr(trials, k=3):
        """
        Quorum Poisoning Rate: Measures the adversary's progress toward 
        controlling a majority of the channels.
        Majority = (k // 2) + 1
        """
        if not trials: return {"metric": "QPR", "avg_value": 0.0, "max_value": 0.0}

        majority_threshold = (k // 2) + 1
        qpr_values = []
        breach_events = 0

        for t in trials:
            num_poisoned = len(t.get('attacked_channels', []))
            # Current poisoning ratio for this specific transmission
            current_qpr = num_poisoned / k
            qpr_values.append(current_qpr)
            
            # Check if majority was actually reached
            if num_poisoned >= majority_threshold:
                breach_events += 1

        avg_qpr = sum(qpr_values) / len(qpr_values)
        max_qpr = max(qpr_values)

        return {
            "metric": "QPR",
            "avg_value": avg_qpr,
            "max_value": max_qpr,
            "display_avg": f"{avg_qpr*100:.2f}%",
            "majority_breached": breach_events > 0,
            "breach_count": breach_events
        }