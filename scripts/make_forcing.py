#!/usr/bin/env python3
"""Build the East River WY2017 forcing: the CW3E hourly forcing for the domain, with the
bias corrections the calibrated case uses, applied in three levels.

    python scripts/make_forcing.py --level 3                      # pull CW3E from HydroData, apply all three corrections
    python scripts/make_forcing.py --raw inputs/forcing/wy2017_raw --level 1
    python scripts/make_forcing.py --raw ... --level 0 --out inputs/forcing/wy2017_raw_copy

Levels (each includes the ones below it):
  0  the raw CW3E subset, as pulled (hourly, one file per day and variable)
  1  per-cell bias correction of precipitation and temperature.  The spatial pattern comes from
     a random-forest model of CW3E biases at SNOTEL stations (9,258 site-years; features:
     elevation, latitude, longitude, CW3E mean temperature and annual precipitation, HUC2);
     the precipitation pattern is rescaled so that its mean at the two in-domain SNOTEL cells
     equals the biases measured there (-14.7 % at Butte, -17.0 % at Schofield Pass).
     Precipitation is divided by (1 + b_P / 100); temperature is shifted by -b_T (the RF
     temperature bias, -0.2 to +0.8 C, unscaled).  Grids: inputs/forcing_correction/
     rf_precip_bias_pct.npy (-29 to -2.5 %), rf_temp_bias_c.npy.
  2  an elevation ramp on precipitation: x1.05 at and below 2500 m rising linearly to x1.22 at
     and above 3400 m.  Calibrated against the SNOTEL snow pillows (the gauges under-catch
     wind-blown snow), with the top trimmed so the highest sites melt out on time.
  3  a valley night-temperature correction: the 1 km CW3E does not resolve the cold-air pool
     of the East River valley (GHCN Crested Butte minima run 4.5 to 8.4 C warm).  Air
     temperature is lowered by 6.5 C x w(z) in hours with zero shortwave, w(z) = 1 at and below
     2750 m falling to 0 at 3000 m, so the correction dies out below the SNOTEL benches.

Level 3 is the calibrated case's forcing.  The pull needs a HydroData account
(https://hydrogen.princeton.edu/signup) and the hf_hydrodata package; the corrections need
only numpy and pftools.  Output: <out>/CW3E.<VAR>.NNNNNN_to_NNNNNN.pfb (+ .dist), 365 days x
8 variables, about 720 MB.
"""
import argparse
import glob
import os
import shutil
import sys

import numpy as np
from parflow.tools.io import read_pfb, write_pfb

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CORR = os.path.join(ROOT, "inputs", "forcing_correction")
VARS = ("APCP", "DLWR", "DSWR", "Press", "SPFH", "Temp", "UGRD", "VGRD")
NDAYS = 365
# the domain's window in the CONUS2 grid (inputs/static/ij_bounds.txt): i0, j0, i1, j1
IJ_BOUNDS = tuple(int(v) for v in open(os.path.join(ROOT, "inputs", "static", "ij_bounds.txt")).read().split(","))

# level 2 and 3 parameters
RAMP_Z_LO, RAMP_Z_HI, RAMP_F_LO, RAMP_F_HI = 2500.0, 3400.0, 1.05, 1.22
NIGHT_A0, NIGHT_Z_FULL, NIGHT_Z_ZERO = 6.5, 2750.0, 3000.0


def pull_raw(out):
    """Subset the CW3E forcing for WY2017 from HydroData into <out> (needs an account)."""
    import subsettools as st
    os.makedirs(out, exist_ok=True)
    st.subset_forcing(IJ_BOUNDS, grid="conus2", start="2016-10-01", end="2017-10-01", dataset="CW3E", write_dir=out)


def day_files(raw, var):
    f = sorted(glob.glob(os.path.join(raw, f"CW3E.{var}.*.pfb")))
    if len(f) != NDAYS:
        sys.exit(f"expected {NDAYS} daily files for {var} in {raw}, found {len(f)}")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=None, help="directory of raw CW3E files (default: pull from HydroData into inputs/forcing/wy2017_raw)")
    ap.add_argument("--level", type=int, default=3, choices=[0, 1, 2, 3])
    ap.add_argument("--out", default=None, help="output directory (default inputs/forcing/wy2017 for level 3, wy2017_levelN otherwise)")
    a = ap.parse_args()
    raw = a.raw or os.path.join(ROOT, "inputs", "forcing", "wy2017_raw")
    if a.raw is None and not glob.glob(os.path.join(raw, "CW3E.APCP.*.pfb")):
        print("pulling the raw CW3E forcing from HydroData ..."); pull_raw(raw)
    out = a.out or os.path.join(ROOT, "inputs", "forcing", "wy2017" if a.level == 3 else f"wy2017_level{a.level}")
    os.makedirs(out, exist_ok=True)
    elev = np.load(os.path.join(CORR, "elevation_m.npy"))                       # (ny, nx)
    bP = np.load(os.path.join(CORR, "rf_precip_bias_pct.npy")); bT = np.load(os.path.join(CORR, "rf_temp_bias_c.npy"))
    p_factor = np.ones_like(elev); t_shift = np.zeros_like(elev)
    if a.level >= 1:
        p_factor = p_factor / np.clip(1.0 + bP / 100.0, 0.2, None); t_shift = t_shift - bT
    if a.level >= 2:
        p_factor = p_factor * np.clip(RAMP_F_LO + (RAMP_F_HI - RAMP_F_LO) * (elev - RAMP_Z_LO) / (RAMP_Z_HI - RAMP_Z_LO), RAMP_F_LO, RAMP_F_HI)
    night_w = np.clip((NIGHT_Z_ZERO - elev) / (NIGHT_Z_ZERO - NIGHT_Z_FULL), 0.0, 1.0) if a.level >= 3 else None
    print(f"level {a.level}: precipitation factor {p_factor.mean():.3f} (basin mean), temperature shift {t_shift.mean():+.2f} C, "
          f"night cooling {'on' if night_w is not None else 'off'}")
    for var in VARS:
        for k, f in enumerate(day_files(raw, var)):
            dst = os.path.join(out, os.path.basename(f))
            if var == "APCP" and a.level >= 1:
                write_pfb(dst, read_pfb(f) * p_factor[None], dist=True)
            elif var == "Temp" and a.level >= 1:
                t = read_pfb(f) + t_shift[None]
                if night_w is not None:
                    sw = read_pfb(os.path.join(raw, os.path.basename(f).replace("Temp", "DSWR")))
                    t = t - NIGHT_A0 * night_w[None] * (sw <= 0.0)
                write_pfb(dst, t, dist=True)
            else:
                shutil.copy(f, dst)
                if os.path.exists(f + ".dist"):
                    shutil.copy(f + ".dist", dst + ".dist")
                else:
                    write_pfb(dst, read_pfb(f), dist=True)
        print(f"  {var}: {NDAYS} days written", flush=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
