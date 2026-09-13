#!/usr/bin/env python3
"""Score a run against the observations: streamflow at the USGS gages, snow water
equivalent at the two SNOTEL pillows, and evapotranspiration at the Pumphouse eddy-flux
tower.  Writes a table and a four-panel figure.

    python scripts/evaluate.py runs/er_wy2017 [--name er_wy2017]

Conventions (they matter; several wrong answers came from getting them wrong):
  * streamflow = overland flow through the gage's cell from ParFlow's kinematic overland
    formulation (parflow.tools.hydrology.calculate_overland_flow_grid, flow_method
    OverlandKinematic), daily mean of the 24 hourly fields, compared with the USGS daily mean;
  * days are LOCAL days: the run starts at 00 UTC on 1 October and model hour h covers UTC
    [h-1, h]; the USGS daily means, the SNOTEL start-of-day readings and the tower are on
    Mountain Standard Time (UTC-7), so hours are shifted by 7 before binning.  Binning on
    UTC days runs about seven hours early;
  * the gage cell is the CONUS2 cell HydroData assigns to the gage number (inputs/obs/sites.csv),
    not the cell under its latitude and longitude;
  * SWE is scored over the whole year and over water-year days 180 to 300 (the melt season):
    bias, RMSE, r, NSE, KGE; never by melt-out day alone;
  * ET means the tower only (et_mm_day_published, 15 Apr to 30 Sep 2017) against the model's
    tower cell.  Both SNOTEL pillows sit in clearings while their model cells are forest, so
    part of any snow misfit is representativeness.
Observations shipped in inputs/obs/: USGS daily discharge (m3/s), NRCS SNOTEL daily SWE (mm),
the tower's daily ET (mm/day; Ryken et al. 2022).
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from parflow.tools.io import read_pfb
from parflow.tools import hydrology as hy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); OBS = os.path.join(ROOT, "inputs", "obs")
DX = DY = 1000.0
WY0 = pd.Timestamp("2016-10-01")
TZ_SHIFT = 7            # hours; MST, the observations' clock


def local_day(hour):
    """model hour h (1-based, covers UTC [h-1, h]) -> local day index (0 = 1 October local)."""
    return (hour - 1 - TZ_SHIFT) // 24


def metrics(m, o):
    ok = np.isfinite(m) & np.isfinite(o); m, o = m[ok], o[ok]
    if len(m) < 3:
        return dict(n=len(m))
    r = np.corrcoef(m, o)[0, 1]
    nse = 1 - np.sum((m - o) ** 2) / np.sum((o - o.mean()) ** 2)
    kge = 1 - np.sqrt((r - 1) ** 2 + (m.std() / o.std() - 1) ** 2 + (m.mean() / o.mean() - 1) ** 2)
    return dict(n=len(m), bias=m.mean() - o.mean(), rmse=np.sqrt(np.mean((m - o) ** 2)), r=r, NSE=nse, KGE=kge)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rundir"); ap.add_argument("--name", default=None, help="run name (default: the .pfidb in rundir)")
    a = ap.parse_args()
    name = a.name or os.path.basename(glob.glob(os.path.join(a.rundir, "*.pfidb"))[0])[:-6]
    rd = a.rundir
    mask = read_pfb(os.path.join(rd, f"{name}.out.mask.pfb")) > 0.5
    sx = read_pfb(os.path.join(rd, f"{name}.out.slope_x.pfb")); sy = read_pfb(os.path.join(rd, f"{name}.out.slope_y.pfb")); mn = read_pfb(os.path.join(rd, f"{name}.out.mannings.pfb"))
    sites = pd.read_csv(os.path.join(OBS, "sites.csv"))
    gages = sites[sites.kind == "streamflow"]; swes = sites[sites.kind == "swe"]; tower = sites[sites.kind == "et_tower"].iloc[0]
    press = {int(f.split(".")[-2]): f for f in glob.glob(os.path.join(rd, f"{name}.out.press.*.pfb"))}
    clm = {int(f.split(".")[-3]): f for f in glob.glob(os.path.join(rd, f"{name}.out.clm_output.*.C.pfb"))}
    hours = sorted(h for h in press if h >= 1)
    ndays = local_day(hours[-1]) + 1
    q = {g.site_id: np.zeros(ndays) for _, g in gages.iterrows()}; nq = np.zeros(ndays)
    swe = {s.site_id: np.zeros(ndays) for _, s in swes.iterrows()}; et = np.zeros(ndays)
    def cell(s):
        i, j = int(s.local_i), int(s.local_j)
        if not mask[-1, j, i]:                                                          # off-mask pillow: nearest active cell
            jj, ii = np.where(mask[-1]); k = np.argmin((ii - i) ** 2 + (jj - j) ** 2); i, j = int(ii[k]), int(jj[k])
        return i, j
    swe_cells = {s.site_id: cell(s) for _, s in swes.iterrows()}
    for h in hours:
        d = local_day(h)
        if d < 0:
            continue
        p = read_pfb(press[h])
        flow = hy.calculate_overland_flow_grid(p, sx, sy, mn, DX, DY, flow_method="OverlandKinematic", mask=mask)   # m3/h per cell
        for _, g in gages.iterrows():
            q[g.site_id][d] += flow[int(g.local_j), int(g.local_i)] / 3600.0
        nq[d] += 1
        if h in clm:
            c = read_pfb(clm[h])
            et[d] += c[4, int(tower.local_j), int(tower.local_i)] * 3600.0            # qflx_evap_tot [mm/s] -> mm per hour
            if (h - 1 - TZ_SHIFT) % 24 == 0:                                             # local midnight: the pillow's start-of-day reading
                for sid, (i, j) in swe_cells.items():
                    swe[sid][d] = c[10, j, i]                                            # swe_out [mm]
        if h % 720 == 0:
            print(f"  hour {h}/{hours[-1]}", flush=True)
    for k in q:
        q[k] = np.where(nq > 0, q[k] / np.maximum(nq, 1), np.nan)
    dates = pd.date_range(WY0, periods=ndays)
    out = pd.DataFrame({"date": dates, **{f"q_{k}": v for k, v in q.items()}, **{f"swe_{k}": v for k, v in swe.items()}, "et_tower": et}).set_index("date")
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    out.to_csv(os.path.join(ROOT, "results", f"{name}_daily.csv"))
    # observations
    qo = pd.read_csv(os.path.join(OBS, "streamflow_daily_wy2017.csv"), parse_dates=["date"]).set_index("date")
    so = pd.read_csv(os.path.join(OBS, "obs_swe_daily.csv"), parse_dates=["date"]).set_index("date")
    eo = pd.read_csv(os.path.join(OBS, "flux_tower_pumphouse_daily.csv"), parse_dates=["date"]).set_index("date")["et_mm_day_published"]
    rows = []
    for gid in qo.columns:
        if f"q_{gid}" in out:
            m = metrics(out[f"q_{gid}"].reindex(qo.index).values, qo[gid].values)
            rows.append(dict(quantity=f"streamflow {gid} [m3/s], daily", **m))
    melt = (out.index >= WY0 + pd.Timedelta(days=180)) & (out.index <= WY0 + pd.Timedelta(days=300))
    for sid in so.columns:
        if f"swe_{sid}" in out:
            mm = out[f"swe_{sid}"].reindex(so.index).values; oo = so[sid].values
            rows.append(dict(quantity=f"SWE {sid} [mm], whole year", **metrics(mm, oo)))
            rows.append(dict(quantity=f"SWE {sid} [mm], WY days 180-300", **metrics(mm[melt[:len(mm)]], oo[melt[:len(oo)]])))
    rows.append(dict(quantity="ET at the tower [mm/day], 15 Apr-30 Sep", **metrics(out["et_tower"].reindex(eo.index).values, eo.values)))
    tab = pd.DataFrame(rows).round(3); tab.to_csv(os.path.join(ROOT, "results", f"{name}_scores.csv"), index=False)
    print(tab.to_string(index=False))
    # figure
    fig, ax = plt.subplots(4, 1, figsize=(10, 12), constrained_layout=True)
    ax[0].plot(qo.index, qo["09112500"], "k", lw=1, label="USGS 09112500 Almont"); ax[0].plot(out.index, out["q_09112500"], "C0", lw=1, label="model"); ax[0].set_ylabel("streamflow [m3/s]")
    for k, sid in enumerate(so.columns):
        ax[1 + k].plot(so.index, so[sid], "k", lw=1, label=f"SNOTEL {sid}"); ax[1 + k].plot(out.index, out[f"swe_{sid}"], "C0", lw=1, label="model"); ax[1 + k].set_ylabel("SWE [mm]")
    ax[3].plot(eo.index, eo, "k.", ms=3, label="tower"); ax[3].plot(out.index, out["et_tower"], "C0", lw=1, label="model"); ax[3].set_ylabel("ET [mm/day]")
    for x in ax:
        x.legend(frameon=False); x.grid(alpha=0.3)
    fig.suptitle(f"East River WY2017: {name}")
    fig.savefig(os.path.join(ROOT, "results", f"{name}_evaluation.png"), dpi=130)
    print("wrote results/" + f"{name}_daily.csv, {name}_scores.csv, {name}_evaluation.png")


if __name__ == "__main__":
    main()
