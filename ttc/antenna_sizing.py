"""Continuous dish aperture sizing against RF power and link requirements."""
import math
from .communications_budget import antenna_options

def minimum_diameter(rf, rate_bps, max_tx_rf_w, minimum_m=0.05,
                     maximum_m=3.0, tolerance_m=0.0001):
    if max_tx_rf_w is None:
        return {"status":"MISSING_RF_POWER_CAP","diameter_m":None}
    if not (math.isfinite(max_tx_rf_w) and max_tx_rf_w>0 and
            0<minimum_m<maximum_m and tolerance_m>0):
        raise ValueError("Invalid sizing bounds or RF power cap")
    def case(d):
        return antenna_options(rf,rate_bps,[d],max_tx_rf_w)["cases"][0]
    upper=case(maximum_m)
    if upper["required_rf_w"] is None:
        return {"status":"INCOMPLETE_LINK_INPUTS","diameter_m":None}
    if upper["within_rf_power_cap"] is not True:
        return {"status":"NO_FEASIBLE_DIAMETER_WITHIN_BOUNDS","diameter_m":None,
                "upper_bound_m":maximum_m,"upper_bound_rf_w":upper["required_rf_w"]}
    lower=case(minimum_m)
    if lower["within_rf_power_cap"]:
        return {"status":"FEASIBLE_AT_MINIMUM_BOUND","diameter_m":minimum_m,
                "link":lower,"assumptions":"Illustrative unless RF inputs validated"}
    lo,hi=minimum_m,maximum_m
    while hi-lo>tolerance_m:
        mid=(lo+hi)/2
        if case(mid)["within_rf_power_cap"]:
            hi=mid
        else:
            lo=mid
    return {"status":"SIZED_WITHIN_BOUNDS","diameter_m":hi,
            "link":case(hi),"assumptions":"Illustrative unless RF inputs validated"}
