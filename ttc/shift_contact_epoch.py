"""Shift historical contact-window timestamps to a future scenario epoch.

This is a calendar translation only, NOT a new orbit propagation.
"""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)

def shift_contacts(source,output,epoch="2030-07-14T22:10:10.811Z"):
    with open(source,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        fields=reader.fieldnames
        rows=list(reader)
    if not rows:raise ValueError("No contacts")
    earliest=min(parse_utc(r["start_utc"]) for r in rows)
    offset=parse_utc(epoch)-earliest
    for r in rows:
        for field in ("start_utc","end_utc"):
            r[field]=(parse_utc(r[field])+offset).isoformat().replace("+00:00","Z")
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
    return len(rows)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="data/contacts_master.csv")
    p.add_argument("--output",default="data/contacts_2030_shifted_scenario.csv")
    p.add_argument("--epoch",default="2030-07-14T22:10:10.811Z")
    a=p.parse_args()
    print("Shifted",shift_contacts(a.input,a.output,a.epoch),"contacts; NOT repropagated")
