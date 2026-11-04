"""SELENA antenna sizing equations supplied from Communications Chapter 2.
All antenna geometry and RF operating points are explicit inputs; no invented link margin.
"""
import csv
import json
import math
from pathlib import Path
from .adaptive_storage import ROOT

C=299792458.0

def antenna(frequency_hz,diameter_m,efficiency,pointing_error_deg=0):
    if frequency_hz<=0 or diameter_m<=0 or not 0<efficiency<=1 or pointing_error_deg<0:
        raise ValueError("Invalid antenna parameters")
    wavelength=C/frequency_hz
    physical_area=math.pi*diameter_m**2/4
    effective_area=efficiency*physical_area
    gain_linear=4*math.pi*effective_area/wavelength**2
    beamwidth_deg=70*wavelength/diameter_m
    pointing_loss_db=-12*(pointing_error_deg/beamwidth_deg)**2
    return dict(wavelength_m=wavelength,physical_area_m2=physical_area,
        effective_area_m2=effective_area,gain_linear=gain_linear,
        gain_dbi=10*math.log10(gain_linear),beamwidth_3db_deg=beamwidth_deg,
        pointing_loss_db=pointing_loss_db)

def link(frequency_hz,distance_m,tx_power_w,tx_gain_linear,tx_line_efficiency,
         rx_gain_linear,tx_pointing_loss_db=0,rx_pointing_loss_db=0):
    if min(frequency_hz,distance_m,tx_power_w,tx_gain_linear,tx_line_efficiency,rx_gain_linear)<=0 or tx_line_efficiency>1:
        raise ValueError("Invalid RF parameters")
    wavelength=C/frequency_hz
    path_gain=(wavelength/(4*math.pi*distance_m))**2
    eirp_w=tx_power_w*tx_gain_linear*tx_line_efficiency
    received_w=eirp_w*path_gain*rx_gain_linear*10**((tx_pointing_loss_db+rx_pointing_loss_db)/10)
    return dict(eirp_w=eirp_w,eirp_dbw=10*math.log10(eirp_w),
        free_space_path_gain_linear=path_gain,free_space_path_loss_db=-10*math.log10(path_gain),
        received_power_w=received_w,received_power_dbw=10*math.log10(received_w),
        note="Received power only: no noise temperature, Eb/N0, BER, coding, atmospheric losses or link margin.")

def required_rate(data_mbit,usable_seconds):
    if data_mbit<0 or usable_seconds<=0: raise ValueError("Invalid data volume/window")
    return data_mbit*1e6/usable_seconds

def evaluate(input_path=None,output_dir=None):
    path=Path(input_path or ROOT/"data"/"antenna_link_inputs.json")
    cfg=json.loads(path.read_text(encoding="utf-8"))
    rows=[]
    for case in cfg["cases"]:
        row={"name":case["name"],"direction":case["direction"],"status":"INCOMPLETE_INPUTS"}
        f=case.get("frequency_hz")
        for side in ("tx","rx"):
            d=case.get(side+"_diameter_m");eta=case.get(side+"_efficiency")
            if f is not None and d is not None and eta is not None:
                for k,v in antenna(f,d,eta,case.get(side+"_pointing_error_deg",0)).items():
                    row[side+"_"+k]=v
        volume=case.get("data_mbit");seconds=case.get("usable_seconds")
        if volume is not None and seconds is not None:
            row["required_bps"]=required_rate(volume,seconds)
        if all(case.get(k) is not None for k in ("distance_m","tx_power_w","tx_line_efficiency")) and f is not None and "tx_gain_linear" in row and "rx_gain_linear" in row:
            row.update(link(f,case["distance_m"],case["tx_power_w"],row["tx_gain_linear"],
                case["tx_line_efficiency"],row["rx_gain_linear"],
                row["tx_pointing_loss_db"],row["rx_pointing_loss_db"]))
            row["status"]="RECEIVED_POWER_ONLY_NOT_LINK_MARGIN"
        rows.append(row)
    out=Path(output_dir or ROOT/"outputs");out.mkdir(parents=True,exist_ok=True)
    result={"status":"PRELIMINARY_NOT_VALIDATED","cases":rows,
      "missing_for_full_link_budget":["receiver_system_noise_temperature_K","required_Eb_N0_dB",
      "modulation_and_coding","additional_losses_dB","frequency_distance_and_antenna_parameters"]}
    (out/"antenna_link_budget.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    with (out/"antenna_link_budget.csv").open("w",newline="",encoding="utf-8") as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    return result

if __name__=="__main__":
    print(json.dumps(evaluate(),indent=2))
