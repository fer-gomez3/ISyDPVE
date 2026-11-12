"""SELENA application-level transfer manifest and selective acknowledgment state.

Conceptual CCSDS-compatible application layer, NOT a CFDP implementation.
Blocks are retained until positively acknowledged; retry only missing blocks.
"""
from dataclasses import dataclass,field
import hashlib

@dataclass
class TransferSession:
    satellite: str
    blocks: dict=field(default_factory=dict)
    confirmed: set=field(default_factory=set)
    transmitted: set=field(default_factory=set)

    def enqueue(self, subsystem, priority, deadline_utc, payload, block_id):
        if not isinstance(payload,bytes):raise TypeError("payload must be bytes")
        if not 1<=int(priority)<=5:raise ValueError("Invalid priority")
        if not payload:raise ValueError("Empty payload")
        if block_id in self.blocks:raise ValueError("Duplicate block ID")
        self.blocks[block_id]={"subsystem":subsystem,"priority":int(priority),
            "deadline_utc":deadline_utc,"payload":payload,
            "sha256":hashlib.sha256(payload).hexdigest(),"size_bytes":len(payload)}
        return block_id

    def manifest(self):
        return [{"block_id":i,"satellite":self.satellite,"subsystem":b["subsystem"],
            "priority":b["priority"],"deadline_utc":b["deadline_utc"],
            "size_bytes":b["size_bytes"],"sha256":b["sha256"],
            "status":"CONFIRMED" if i in self.confirmed else
                     "TRANSMITTED_UNCONFIRMED" if i in self.transmitted else "PENDING"}
            for i,b in sorted(self.blocks.items(),key=lambda item:(item[1]["deadline_utc"],-item[1]["priority"],item[0]))]

    def transmit(self, byte_budget):
        if byte_budget<0:raise ValueError("Negative budget")
        chosen=[]
        for item in self.manifest():
            i=item["block_id"]
            if i in self.confirmed:continue
            if item["size_bytes"]>byte_budget:continue
            byte_budget-=item["size_bytes"]
            self.transmitted.add(i)
            chosen.append(i)
        return chosen

    def acknowledge(self, received):
        for i in received:
            if i not in self.blocks or i not in self.transmitted:
                raise ValueError("ACK for unknown or unsent block")
            self.confirmed.add(i)

    def release_confirmed(self):
        count=0
        for i in list(self.confirmed):
            del self.blocks[i]
            self.transmitted.discard(i)
            self.confirmed.discard(i)
            count+=1
        return count

    @property
    def stored_bytes(self):
        return sum(b["size_bytes"] for b in self.blocks.values())
