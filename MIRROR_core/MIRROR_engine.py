import hashlib
from collections import Counter

class MirrorEngine:
    def __init__(self, k=3, num_text_carriers=2, max_ghost_channels=1):
        self.k = k
        self.num_text_carriers = num_text_carriers
        self.max_ghost_channels = max_ghost_channels
        self.active_channel_ids = list(range(k))
        self.ghost_history = [] 

    def _get_hash(self, text):
        if text is None: return "NULL_CONTENT"
        return hashlib.sha256(str(text).encode('utf-8')).hexdigest()

    def prepare_packets(self, message):
        msg_hash = self._get_hash(message)
        packets = []
        for i in range(self.k):
            logic_id = self.active_channel_ids[i]
            packet = {'logic_id': logic_id, 'hash': msg_hash, 'channel_index': i}
            
            if i < self.num_text_carriers:
                packet.update({'type': 'text', 'content': message})
            else:
                packet.update({'type': 'witness', 'content': None})
            packets.append(packet)
        return packets

    def resolve(self, candidates):
        if self.k == 1:
            content = candidates[0].get('content', "[MIRROR_ERROR: EMPTY_CHANNEL]")
            return str(content), []

        # ENFORCED MAJORITY VOTING
        votes = [c.get('hash', 'DROPPED') for c in candidates]
        winner_hash, count = Counter(votes).most_common(1)[0]
        
        # This triggers [MIRROR_BLOCK] if two attackers provide different poisons
        consensus_reached = count > (self.k / 2)

        # BYZANTINE AUDIT
        traitors = []
        for i, c in enumerate(candidates):
            # A channel is a traitor if its hash is wrong OR if its content 
            # doesn't match its own reported hash (spoofing check)
            if c.get('hash') != winner_hash:
                traitors.append(i)
            elif c.get('type') == 'text' and self._get_hash(c.get('content')) != winner_hash:
                if i not in traitors: traitors.append(i)

        # 3. GHOST ROTATION (FIFO Strategy)
        if traitors:
            self._rotate_ghost_channels(traitors)

        # 4. RECOVERY
        if consensus_reached:
            for c in candidates:
                if c.get('type') == 'text' and self._get_hash(c.get('content')) == winner_hash:
                    return str(c['content']), traitors
            return "[MIRROR_ERROR: DATA_INTEGRITY_VIOLATION]", traitors
            
        # If consensus fails, we block. This is the 'Safe State'
        return "[MIRROR_BLOCK: NO_CONSENSUS]", traitors

    def _rotate_ghost_channels(self, traitors):
        """Replaces compromised channels and drops oldest ghost (FIFO)."""
        for t_idx in traitors:
            new_id = max(self.active_channel_ids + self.ghost_history + [0]) + 1
            self.ghost_history.append(new_id)

            if len(self.ghost_history) > self.max_ghost_channels:
                dropped = self.ghost_history.pop(0)
                print(f"[BLUE TEAM] FIFO: Dropping oldest ghost reference {dropped}")

            self.active_channel_ids[t_idx] = new_id
            print(f"[BLUE TEAM] ROTATION: Slot {t_idx} is now Ghost ID {new_id}")