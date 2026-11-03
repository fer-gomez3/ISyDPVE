"""Preliminary Earth-link RF, electrical and thermal interface model.

All inputs are explicit scenario assumptions. No equipment selection is implied.
"""
import math

C = 299792458.0
K_DBW_PER_K_HZ = -228.6

def evaluate(link, contact_hours=None):
    """Return a link budget and EPS/TCS interfaces; unknown inputs stay None.

    Required keys for RF: distance_km, frequency_hz, tx_gain_dbi,
    rx_gt_db_per_k, data_rate_bps, required_ebn0_db, losses_db, margin_db.
    Optional tx_rf_w overrides the computed minimum to evaluate actual margin.
    Electrical: pa_efficiency (0..1], electronics_w >=0, standby_w >=0.
    """
    keys=("distance_km","frequency_hz","tx_gain_dbi","rx_gt_db_per_k",
          "data_rate_bps","required_ebn0_db","losses_db","margin_db")
    missing=[k for k in keys if link.get(k) is None]
    out={"status":"INCOMPLETE" if missing else "SCENARIO","missing_inputs":missing,
         "assumptions":link,"fspl_db":None,"minimum_rf_w":None,
         "chosen_rf_w":None,"achieved_ebn0_db":None,"link_margin_db":None,
         "tx_dc_w":None,"tx_standby_w":link.get("standby_w"),
         "tx_energy_wh":None,"tx_heat_w":None,"contact_hours":contact_hours}
    if missing:
        return out
    distance=float(link["distance_km"])*1000
    freq=float(link["frequency_hz"])
    rate=float(link["data_rate_bps"])
    if min(distance,freq,rate)<=0: raise ValueError("distance, frequency and rate must be positive")
    fspl=20*math.log10(4*math.pi*distance*freq/C)
    # Eb/N0 = EIRP - path losses + G/T - k - 10log10(bit rate)
    # EIRP = RF power in dBW + transmit antenna gain.
    required_eirp=(float(link["required_ebn0_db"])+float(link["margin_db"])
                   +fspl+float(link["losses_db"])+K_DBW_PER_K_HZ
                   +10*math.log10(rate)-float(link["rx_gt_db_per_k"]))
    min_rf=10**((required_eirp-float(link["tx_gain_dbi"]))/10)
    rf=float(link["tx_rf_w"]) if link.get("tx_rf_w") is not None else min_rf
    if rf<=0: raise ValueError("RF power must be positive")
    achieved=(10*math.log10(rf)+float(link["tx_gain_dbi"])-fspl
              -float(link["losses_db"])+float(link["rx_gt_db_per_k"])
              -K_DBW_PER_K_HZ-10*math.log10(rate))
    out.update(fspl_db=fspl,minimum_rf_w=min_rf,chosen_rf_w=rf,
               achieved_ebn0_db=achieved,
               link_margin_db=achieved-float(link["required_ebn0_db"]),
               status="SCENARIO_LINK_CHECKED")
    efficiency=link.get("pa_efficiency")
    electronics=link.get("electronics_w")
    if efficiency is not None and electronics is not None:
        eff=float(efficiency); electronics=float(electronics)
        if not 0<eff<=1 or electronics<0: raise ValueError("Invalid PA efficiency or electronics power")
        dc=rf/eff+electronics
        out["tx_dc_w"]=dc
        out["tx_heat_w"]=dc-rf
        if contact_hours is not None:
            if contact_hours<0: raise ValueError("Invalid contact hours")
            out["tx_energy_wh"]=dc*contact_hours
    return out
