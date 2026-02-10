import json
import time
import os
import random
import uuid

class BaseTransport:
    def send(self, payload):
        raise NotImplementedError

class InMemoryTransport(BaseTransport):
    """Direct object reference. Fast, but unrealistic."""
    def send(self, payload):
        return payload

class JsonFileTransport(BaseTransport):
    """
    Simulates a Message Queue or Shared Drive. 
    Vulnerable to file-system level attacks, but immune to network sniffers.
    """
    def send(self, payload):
        # 1. Serialize
        data = json.dumps(payload)
        
        # 2. Write to "Network" (Disk)
        filename = f"network_packet_{uuid.uuid4()}.json"
        with open(filename, "w") as f:
            f.write(data)
            
        # 3. Simulate "Transport Time"
        time.sleep(0.01) 
        
        # 4. Read from "Network"
        with open(filename, "r") as f:
            received_data = json.load(f)
            
        # 5. Cleanup
        os.remove(filename)
        
        return received_data

class SimulatedNetworkTransport(BaseTransport):
    """
    Simulates HTTP/REST over TCP/IP.
    Forces strict serialization and adds latency.
    """
    def send(self, payload):
        # 1. Packetization (Headers + Body)
        packet = {
            "headers": {"Content-Type": "application/json", "TTL": 64},
            "body": payload
        }
        
        # 2. Wire Serialization (Bytes)
        wire_data = json.dumps(packet).encode('utf-8')
        
        # 3. Latency Simulation (Network Lag)
        # Random lag between 50ms and 100ms
        time.sleep(random.uniform(0.05, 0.1))
        
        # 4. Deserialization (The receiving server parsing the request)
        received_packet = json.loads(wire_data.decode('utf-8'))
        
        return received_packet["body"]