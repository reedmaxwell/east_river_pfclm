# East River ParFlow-CLM test case

A real-watershed, coupled ParFlow-CLM simulation you can run on a laptop: the East River
headwaters of the Gunnison, Colorado (Upper Colorado basin), as a 32 by 41 by 10 subset of
the CONUS2.1 model at 1 km, for water year 2017, with observations to score it against.
One flat Python script holds every key.  A full year takes about five minutes on one core.

The case is the calibrated configuration from the TFG_smoother East River test bed
(Maxwell, 2026): CONUS2.1 static inputs, CW3E forcing with three documented bias
corrections, calibrated geology and Manning's fields, the CLM5-style snow and canopy
physics in ParFlow 3.15, and the solver settings that ran fastest on it.

## Prerequisites

- ParFlow 3.15.0 or later, built with CLM (`-DPARFLOW_HAVE_CLM=ON`) and as a Release build.
  Set `PARFLOW_DIR` to the install.  The surface ponding predictor this case uses was fixed in
  ParFlow pull request 761 (September 2026); earlier versions run but converge slower.
- Python 3.10+ with `pftools` (ships with ParFlow: `pip install pftools`), `numpy`,
  `pandas`, `matplotlib`; `xarray` and `netCDF4` for the NetCDF converter; `hf_hydrodata`
  and `subsettools` only if you rebuild the forcing from HydroData (needs an account at
  https://hydrogen.princeton.edu/signup).
- GitHub Codespaces: `.devcontainer/` builds ParFlow with CLM from the release tag and installs
  the Python packages.  The container is untested as of this writing; the forcing download in
  `postCreateCommand` is the slow step (330 MB compressed).

## Quick start

```bash
git clone https://github.com/reedmaxwell/east_river_pfclm.git && cd east_river_pfclm
bash scripts/get_forcing.sh                       # the corrected WY2017 forcing, from the release assets
python scripts/run_east_river.py                  # runs/er_wy2017/, hourly output, ~5 min
python scripts/evaluate.py runs/er_wy2017         # scores + figure in results/
python scripts/pfb_to_netcdf.py runs/er_wy2017    # optional: one NetCDF per variable
```

A shorter test: `python scripts/run_east_river.py --hours 240 --name er_10days`.

## The domain

- 32 x 41 columns of 1 km, 721 active, from the CONUS2.1 grid (`inputs/static/ij_bounds.txt`
  gives the window: i 1359 to 1391, j 1577 to 1618).  The outlet is the USGS gage East River
  at Almont (09112500), 750 km2.
- 10 layers, 200 m total: 100, 50, 25, 12.5, 5, 2.5, 0.5, 0.3, 0.15, 0.05 m from the bottom up
  (variable dz).  The top metre holds the CONUS2.1 soil classes, below is geology.
- Terrain-following grid, kinematic overland flow on the top patch, no-flow bottom and sides.

## Inputs and where they come from

| file | what | source |
|---|---|---|
| `inputs/static/solidfile.pfsol`, `pf_indicator.pfb` | domain solid and the soil / geology indicator | CONUS2.1 via HydroData (`subsettools`) |
| `inputs/static/slope_x.pfb`, `slope_y.pfb` | topographic slopes | CONUS2.1 |
| `inputs/static/mannings.pfb` | Manning's n: channel network 0.12, hillslopes 0.045 (ParFlow units, hr m^-1/3 scaled) | calibrated (drainage-area network) |
| `inputs/static/pf_flowbarrier.pfb` | vertical flow barrier at the soil-bedrock interface | CONUS2.1 |
| `inputs/initial/ic_pressure.pfb`, `clm_restart.rst` | spun-up pressure and CLM state at 1 Oct 2016 | cyclic WY2017 coupled spin-up of this configuration |
| `inputs/clm/drv_clmin.dat`, `drv_vegm.dat`, `drv_vegp.dat` | CLM driver, vegetation map, vegetation parameters | CONUS2.1 via HydroData, with the calibrated parameters (see Physics) |
| `inputs/forcing/wy2017/` | hourly CW3E forcing, corrected (720 MB, not in git) | release asset, or `scripts/make_forcing.py` |
| `inputs/forcing_correction/` | the per-cell bias grids and the elevation map | see Forcing |
| `inputs/obs/` | USGS daily discharge, SNOTEL daily SWE, tower ET, and the site-to-cell table | USGS NWIS, NRCS, Ryken et al. (2022) |

## Forcing and its bias correction

CW3E is a 1 km hourly reanalysis-based product.  In this basin it under-catches
orographic precipitation and does not resolve the valley's night-time cold-air pool.
`scripts/make_forcing.py` builds the forcing from the raw HydroData pull in three levels,
each including the ones below; level 3 is what the calibrated case uses and what the
release tarball contains.

| level | correction | how it was set |
|---|---|---|
| 0 | raw CW3E subset | `subsettools.subset_forcing` |
| 1 | per-cell precipitation and temperature bias: a random-forest model of CW3E biases at SNOTEL stations (9,258 site-years) gives the spatial pattern; the precipitation pattern is rescaled so its mean at the two in-domain SNOTEL cells matches the measured biases, -14.7 % (Butte) and -17.0 % (Schofield Pass); precipitation is divided by (1 + b/100), temperature shifted by -b_T | measured at the pillows and gauges |
| 2 | an elevation ramp on precipitation, x1.05 at 2500 m rising to x1.22 at 3400 m | calibrated to the SNOTEL snow pillows (gauges under-catch wind-blown snow), top trimmed so the high sites melt out on time |
| 3 | night-time cooling of air temperature by 6.5 C, full at and below 2750 m, zero at 3000 m, in hours with no shortwave | GHCN Crested Butte minima are 4.5 to 8.4 C warm in the raw forcing |

Precipitation at the basin scale ends up 1.40 times the raw product.  Try `--level 0` to
see what the uncorrected forcing does to the snowpack and the hydrograph.

## Physics configuration

- van Genuchten soils and geology with lookup tables (100,000 points) for speed.
- Geology: eight CONUS2.1 units with permeability tripled (0.06 to 0.60 m/h), vertical
  anisotropy 0.1; the recession lever of the calibration.
- CLM: Medlyn stomatal conductance, CLM5 tanh interception, a snow-cover fraction with a
  solar-zenith-angle term, five root-zone layers, saturation-based vegetation water
  stress.  All in ParFlow 3.15.

## Solver configuration

The settings in `run_east_river.py` are the ones that ran fastest on this case, measured
hour by hour and over the year on a single core:

| setting | effect on this case |
|---|---|
| `Solver.Linear.Preconditioner.PCMatrixType PFSymmetric` | the preconditioner is built from the symmetric part of the Jacobian; linear iterations halve, Newton iterations unchanged, wall time 0.66 of the full-Jacobian preconditioner |
| `Solver.SurfacePredictor True` with `LateralFlows True` | a surface ponding predictor for the initial guess; Newton iterations 0.94, wall time 0.60 of the control together with the line above |
| `Solver.Nonlinear.EtaChoice EtaConstant`, `EtaValue 0.01` | linear solves to a fixed relative tolerance; the adaptive (Walker2) forcing was 3 % slower here |
| `Solver.Linear.Preconditioner PFMGOctree` at its defaults | the PFMG relaxation, cycle, and smoother settings, SMG, and the Krylov dimension were swept: within noise |
| one-hour constant time step | CLM's coupling interval |

Reference timings and the validation scores are in the next section.

## What the case reproduces

Scores of `run_east_river.py` as shipped, on ParFlow v3.15.0 (Release build, CLM, one core
of an Apple M-series laptop), from `scripts/evaluate.py`.  Daily values, water year 2017.

| quantity | bias | RMSE | r | NSE | KGE |
|---|---|---|---|---|---|
| streamflow, East River at Almont 09112500 [m3/s] | +1.5 | 7.1 | 0.91 | 0.82 | 0.85 |
| streamflow, East River below Cement Creek 09112200 [m3/s] | +1.4 | 6.4 | 0.93 | 0.84 | 0.86 |
| streamflow, Slate River above Baxter Gulch [m3/s] | -1.3 | 3.7 | 0.90 | 0.75 | 0.61 |
| SWE, Butte SNOTEL 380 [mm], whole year | -16 | 38 | 0.99 | 0.97 | 0.86 |
| SWE, Butte SNOTEL 380 [mm], melt season (WY days 180-300) | -32 | 60 | 1.00 | 0.92 | 0.70 |
| SWE, Schofield Pass SNOTEL 737 [mm], whole year | -28 | 130 | 0.97 | 0.93 | 0.84 |
| SWE, Schofield Pass SNOTEL 737 [mm], melt season | +3 | 202 | 0.95 | 0.85 | 0.70 |
| ET, Pumphouse tower [mm/day], 15 Apr to 30 Sep | -0.10 | 0.80 | 0.76 | 0.54 | 0.74 |

`results/er_wy2017_evaluation.png` shows the four series.  The observed peak at Almont is
72 m3/s and the model's 66; the annual mean is 11.9 against 13.4 m3/s.  Schofield Pass melts
out about three weeks late and peaks 20 % low: the pillow sits in a clearing and its model
cell is forest, so part of that is representativeness, not error.  Butte melts out within a
day of the pillow.

Cost: 8,760 hourly steps in 375 s wall time on one core, 311 s of it in the nonlinear
solver; 53,825 Newton iterations, 223,289 linear iterations, 82,300 function
evaluations.  Hourly output for the year is about 2 GB.

The calibrated configuration was developed on a ParFlow feature branch with two CLM
soil-moisture-stress keys that ParFlow 3.15 does not have.  Without them the hydrograph
is unchanged (NSE 0.82 against 0.82 on the same forcing) and the end-of-year subsurface
state differs by 0.35 m RMS, so treat the initial condition as approximate to this build.

## Outputs

Hourly PFB files in `runs/<name>/`: pressure (`*.out.press.NNNNN.pfb`, m, 10 layers), CLM's
flux into ParFlow (`*.out.evaptrans.*`), and the single-file CLM output
(`*.out.clm_output.NNNNN.C.pfb`: latent, longwave, sensible and ground heat fluxes, total /
ground / soil / vegetation evaporation, transpiration, infiltration, SWE, ground temperature,
irrigation, soil temperatures).  `scripts/pfb_to_netcdf.py` collects any of them into one
NetCDF file per variable; `run_east_river.py --netcdf` writes NetCDF directly if ParFlow
was built with it.

`scripts/evaluate.py` scores streamflow at the gages, SWE at the two pillows, and ET at the
tower with the conventions in its docstring (local days, the gage's CONUS2 cell, melt-season
window), and writes `results/<name>_scores.csv` and a four-panel figure.

## Troubleshooting

- `Can't open the distribution file X.pfb.dist`: the run script distributes the inputs it
  copies; if you point at your own files, call `run.dist(file)` or `pfdist`.
- CLM stops at once with a header error: `drv_vegm.dat` must keep its classic two-line
  header; do not add comment lines.
- The solver fails in the first hours after you change the initial condition: the initial
  pressure and the CLM restart are a matched pair from the same spin-up; replace both or
  neither.
- ParFlow silently ignores keys it does not know.  If a physics option seems to do nothing,
  check the ParFlow version.

## File structure

```
scripts/run_east_river.py     the whole model definition, one flat script
scripts/make_forcing.py       raw CW3E pull + the three bias-correction levels
scripts/get_forcing.sh        download the corrected forcing from the release
scripts/evaluate.py           scores against USGS, SNOTEL, and the tower
scripts/pfb_to_netcdf.py      PFB -> NetCDF
inputs/static, clm, initial, forcing_correction, obs
.devcontainer/                GitHub Codespaces / VS Code container
```

## References

- CONUS2.1 static inputs and the CW3E forcing: HydroFrame / HydroData (https://hydroframe.org),
  accessed with `subsettools` and `hf_hydrodata`.
- The Pumphouse eddy-flux tower: Ryken et al. (2021), the East River SFA.
- ParFlow: Maxwell et al., ParFlow user manual and https://github.com/parflow/parflow;
  Kuffour et al. (2020), Simulating coupled surface-subsurface flows with ParFlow v3.5.0,
  Geoscientific Model Development.
