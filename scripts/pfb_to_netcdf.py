#!/usr/bin/env python3
"""Collect a run's hourly PFB output into one NetCDF file per variable, for easy access with
xarray.  Works with any ParFlow build (no NetCDF support needed at run time).

    python scripts/pfb_to_netcdf.py runs/er_wy2017 [--vars press,satur,clm] [--out runs/er_wy2017/netcdf]

Variables: press (pressure head, m, 10 layers), satur (if written), evaptrans (CLM's flux into
ParFlow, 1/h per cell), clm (the single-file CLM output: layers listed in the file's attributes).
Time is hours since 2016-10-01 00:00 UTC.  Needs xarray; netCDF4 for compressed NetCDF4 files (falls back to scipy's NetCDF3 without it).
"""
import argparse
import glob
import os

import numpy as np
import xarray as xr
from parflow.tools.io import read_pfb

CLM_LAYERS = ["eflx_lh_tot W/m2", "eflx_lwrad_out W/m2", "eflx_sh_tot W/m2", "eflx_soil_grnd W/m2", "qflx_evap_tot mm/s", "qflx_evap_grnd mm/s",
              "qflx_evap_soi mm/s", "qflx_evap_veg mm/s", "qflx_tran_veg mm/s", "qflx_infl mm/s", "swe_out mm", "t_grnd K", "qflx_qirr mm/s", "tsoil K (top soil layers follow)"]


def collect(rundir, name, var, out):
    pat = {"press": "press", "satur": "satur", "evaptrans": "evaptrans", "clm": "clm_output"}[var]
    files = sorted(glob.glob(os.path.join(rundir, f"{name}.out.{pat}.*.pfb")))
    if not files:
        print(f"  no {var} files"); return
    hours = [int(f.split(".")[-2 if var != "clm" else -3]) for f in files]
    data = np.stack([read_pfb(f) for f in files])
    dims = ("time", "z", "y", "x") if data.ndim == 4 else ("time", "y", "x")
    da = xr.DataArray(data, dims=dims, coords={"time": hours}, name=var, attrs={"units": {"press": "m", "satur": "-", "evaptrans": "1/h", "clm": "see layer_names"}[var]})
    if var == "clm":
        da.attrs["layer_names"] = "; ".join(f"{k}: {v}" for k, v in enumerate(CLM_LAYERS))
    da.coords["time"].attrs["units"] = "hours since 2016-10-01 00:00:00"
    try:
        import netCDF4  # noqa: F401  (compression needs the netCDF4 backend)
        da.to_netcdf(os.path.join(out, f"{name}.{var}.nc"), engine="netcdf4", encoding={var: {"zlib": True, "complevel": 4}})
    except ImportError:
        print("  (netCDF4 not installed: writing uncompressed NetCDF3 through scipy; pip install netCDF4 for compression)")
        da.to_netcdf(os.path.join(out, f"{name}.{var}.nc"))
    print(f"  {var}: {len(files)} files -> {name}.{var}.nc")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rundir"); ap.add_argument("--name", default=None); ap.add_argument("--vars", default="press,evaptrans,clm"); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    name = a.name or os.path.basename(glob.glob(os.path.join(a.rundir, "*.pfidb"))[0])[:-6]
    out = a.out or os.path.join(a.rundir, "netcdf"); os.makedirs(out, exist_ok=True)
    for v in a.vars.split(","):
        collect(a.rundir, name, v.strip(), out)


if __name__ == "__main__":
    main()
