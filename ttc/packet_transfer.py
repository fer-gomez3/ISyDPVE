"""Application-level fragment transfer with resumable selective ACK state.

Demonstrator only: not a CCSDS CFDP wire implementation or radio simulator.
The state can be checkpointed to JSON between simulated contacts.
"""
import base64
import hashlib
import json
from pathlib import Path

class PacketTransfer:
    def __init__(self,spacecraft,fragment_bytes=1024):
        if fragment_bytes<=0:raise ValueError("Invalid fragment size")
        self.spacecraft=spacecraft
        self.fragment_bytes=fragment_bytes
        self.files={}
        self.sent=set()
        self.acked=set()

    def enqueue(self,file_id,payload,*,priority=3,deadline_utc=""):
        if file_id in self.files or not isinstance(payload,bytes) or not payload:
            raise ValueError("Duplicate file, empty or invalid payload")
        if not 1<=priority<=5:raise ValueError("Invalid priority")
        fragments=[payload[i:i+self.fragment_bytes] for i in range(0,len(payload),self.fragment_bytes)]
        self.files[file_id]={"priority":priority,"deadline_utc":deadline_utc,
            "fragments":fragments,"sha256":hashlib.sha256(payload).hexdigest()}

    def _ordered(self):
        for fid,f in sorted(self.files.items(),key=lambda item:(item[1]["deadline_utc"],-item[1]["priority"],item[0])):
            for index,payload in enumerate(f["fragments"]):
                key=(fid,index)
                if key not in self.acked:
                    yield key,payload

    def transmit(self,byte_budget):
        if byte_budget<0:raise ValueError("Invalid budget")
        packets=[]
        for key,payload in self._ordered():
            if len(payload)>byte_budget:continue
            byte_budget-=len(payload)
            self.sent.add(key)
            packets.append({"file_id":key[0],"fragment_index":key[1],
                "fragment_count":len(self.files[key[0]]["fragments"]),
                "payload":payload,"sha256":hashlib.sha256(payload).hexdigest()})
        return packets

    def acknowledge(self,packet_ids):
        for file_id,index in packet_ids:
            key=(file_id,index)
            if key not in self.sent:raise ValueError("ACK for unsent packet")
            self.acked.add(key)

    def complete_files(self):
        return [fid for fid,f in self.files.items()
            if all((fid,i) in self.acked for i in range(len(f["fragments"])))]

    def release_confirmed(self):
        complete=self.complete_files()
        for fid in complete:
            del self.files[fid]
        self.sent={key for key in self.sent if key[0] in self.files}
        self.acked={key for key in self.acked if key[0] in self.files}
        return complete

    def checkpoint(self,path):
        data={"spacecraft":self.spacecraft,"fragment_bytes":self.fragment_bytes,
              "files":{fid:{"priority":f["priority"],"deadline_utc":f["deadline_utc"],
                  "sha256":f["sha256"],"fragments":[base64.b64encode(x).decode("ascii") for x in f["fragments"]]}
                  for fid,f in self.files.items()},
              "sent":[list(x) for x in sorted(self.sent)],
              "acked":[list(x) for x in sorted(self.acked)]}
        Path(path).write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")

    @classmethod
    def restore(cls,path):
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        obj=cls(data["spacecraft"],data["fragment_bytes"])
        for fid,f in data["files"].items():
            payload=b"".join(base64.b64decode(x) for x in f["fragments"])
            if hashlib.sha256(payload).hexdigest()!=f["sha256"]:
                raise ValueError("Corrupt checkpoint payload")
            obj.enqueue(fid,payload,priority=f["priority"],deadline_utc=f["deadline_utc"])
        obj.sent={tuple(x) for x in data["sent"]}
        obj.acked={tuple(x) for x in data["acked"]}
        valid={(fid,i) for fid,f in obj.files.items() for i in range(len(f["fragments"]))}
        if not obj.acked<=obj.sent or not obj.sent<=valid:raise ValueError("Invalid checkpoint state")
        return obj
