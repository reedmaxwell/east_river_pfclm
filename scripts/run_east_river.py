#!/usr/bin/env python3
"""Run the East River ParFlow-CLM test case for one water year.

Everything is in this one file: the grid, the subsurface, the boundary conditions, CLM,
the solver, and the outputs.  Edit values here; there is no hidden configuration.

    python scripts/run_east_river.py --forcing inputs/forcing/wy2017 [--hours 8760] [--name er_wy2017]
                                     [--np 1] [--netcdf]

Needs: ParFlow >= 3.15 with CLM (PARFLOW_DIR set), the pftools Python package that ships
with it, and the inputs described in README.md.  Runs in ./runs/<name>/ (created).
"""
import argparse
import os
import shutil
import sys

from parflow import Run
from parflow.tools.fs import mkdir

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--forcing", default=os.path.join(ROOT, "inputs", "forcing", "wy2017"), help="directory of CW3E.<VAR>.NNNNNN_to_NNNNNN.pfb files")
ap.add_argument("--hours", type=int, default=8760, help="hours to simulate (8760 = the full water year)")
ap.add_argument("--name", default="er_wy2017", help="run name (output prefix)")
ap.add_argument("--np", type=int, default=1, help="MPI processes (P x Q decomposition is set below)")
ap.add_argument("--netcdf", action="store_true", help="also write NetCDF output (needs a ParFlow built with NetCDF)")
args = ap.parse_args()

rundir = os.path.join(ROOT, "runs", args.name)
mkdir(rundir)
for f in ("solidfile.pfsol", "pf_indicator.pfb", "slope_x.pfb", "slope_y.pfb", "mannings.pfb", "pf_flowbarrier.pfb"):
    shutil.copy(os.path.join(ROOT, "inputs", "static", f), rundir)
for f in ("drv_clmin.dat", "drv_vegm.dat", "drv_vegp.dat"):
    shutil.copy(os.path.join(ROOT, "inputs", "clm", f), rundir)
shutil.copy(os.path.join(ROOT, "inputs", "initial", "ic_pressure.pfb"), rundir)
shutil.copy(os.path.join(ROOT, "inputs", "initial", "clm_restart.rst"), os.path.join(rundir, "washita.rst.00000.0"))   # CLM's fixed restart name
os.chdir(rundir)

er = Run(args.name)                      # working directory = rundir (we changed into it above)

# ---------------------------------------------------------------- processors and grid
er.FileVersion = 4
er.Process.Topology.P = args.np          # split along x; set Q for a 2-D decomposition
er.Process.Topology.Q = 1
er.Process.Topology.R = 1

er.ComputationalGrid.Lower.X = 0.0       # 1 km cells, 32 x 41 columns (a CONUS2.1 subset), 10 layers
er.ComputationalGrid.Lower.Y = 0.0
er.ComputationalGrid.Lower.Z = 0.0
er.ComputationalGrid.DX = 1000.0
er.ComputationalGrid.DY = 1000.0
er.ComputationalGrid.DZ = 200.0          # times the dzScale list below: 200, 100, 50, 25, 10, 5, 1, 0.6, 0.3, 0.1 m
er.ComputationalGrid.NX = 32
er.ComputationalGrid.NY = 41
er.ComputationalGrid.NZ = 10

er.Solver.Nonlinear.VariableDz = True
er.dzScale.GeomNames = "domain"
er.dzScale.Type = "nzList"
er.dzScale.nzListNumber = 10
for k, s in enumerate((1.0, 0.5, 0.25, 0.125, 0.05, 0.025, 0.005, 0.003, 0.0015, 0.0005)):
    er.Cell[str(k)].dzScale.Value = s    # bottom (k = 0) to top (k = 9)

# ---------------------------------------------------------------- domain and geologic units
er.GeomInput.Names = "domaininput indi_input"
er.GeomInput.domaininput.InputType = "SolidFile"
er.GeomInput.domaininput.GeomNames = "domain"
er.GeomInput.domaininput.FileName = "solidfile.pfsol"
er.Geom.domain.Patches = "top bottom side"
er.Domain.GeomName = "domain"

# the indicator file holds the CONUS2.1 soil classes (1-13) and geology classes (19-28)
er.GeomInput.indi_input.InputType = "IndicatorField"
er.GeomInput.indi_input.GeomNames = "s1 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 s12 s13 g1 g2 g3 g4 g5 g6 g7 g8 b1 b2"
er.Geom.indi_input.FileName = "pf_indicator.pfb"
INDICATOR = {"s1": 1, "s2": 2, "s3": 3, "s4": 4, "s5": 5, "s6": 6, "s7": 7, "s8": 8, "s9": 9, "s10": 10, "s11": 11, "s12": 12, "s13": 13,
             "b1": 19, "b2": 20, "g1": 21, "g2": 22, "g3": 23, "g4": 24, "g5": 25, "g6": 26, "g7": 27, "g8": 28}
for name, val in INDICATOR.items():
    er.GeomInput[name].Value = val

# ---------------------------------------------------------------- subsurface properties
# permeability [m/h], porosity, van Genuchten alpha [1/m], n, residual saturation.
# Soils: CONUS2.1 classes.  Geology: the calibrated East River values (3 x the CONUS2.1
# bedrock permeability, the recession lever).  Vertical anisotropy 0.1 in the geology.
SOILS = {  # name: (perm, porosity, alpha, n, sres)
    "s1": (0.087, 0.375, 3.548, 3.2, 0.01), "s2": (0.055, 0.390, 3.467, 2.0, 0.01), "s3": (0.031, 0.387, 2.692, 2.0, 0.02),
    "s4": (0.019, 0.439, 0.501, 2.0, 0.02), "s5": (0.042, 0.489, 0.661, 2.0, 0.02), "s6": (0.014, 0.399, 1.122, 2.0, 0.02),
    "s7": (0.016, 0.384, 2.089, 2.0, 0.03), "s8": (0.020, 0.482, 0.832, 2.0, 0.03), "s9": (0.025, 0.442, 1.585, 2.0, 0.03),
    "s10": (0.079, 0.385, 2.800, 2.0, 0.04), "s11": (0.081, 0.481, 0.800, 2.0, 0.05), "s12": (0.045, 0.459, 0.800, 2.0, 0.05),
    "s13": (0.014, 0.399, 1.122, 2.0, 0.02)}
GEOLOGY = {  # name: (perm, porosity, vertical anisotropy or None)
    "g1": (0.06, 0.12, 0.1), "g2": (0.09, 0.30, 0.1), "g3": (0.12, 0.01, None), "g4": (0.15, 0.15, 0.1), "g5": (0.18, 0.22, 0.1),
    "g6": (0.24, 0.27, 0.1), "g7": (0.30, 0.06, 0.1), "g8": (0.60, 0.30, None), "b1": (0.005, 0.05, 0.1), "b2": (0.01, 0.10, 0.1)}

er.Geom.Perm.Names = "domain " + " ".join(list(SOILS) + list(GEOLOGY))
er.Geom.domain.Perm.Type = "Constant"
er.Geom.domain.Perm.Value = 0.02          # fallback where the indicator has no class
for name, (perm, poro, alpha, n, sres) in SOILS.items():
    er.Geom[name].Perm.Type = "Constant"
    er.Geom[name].Perm.Value = perm
for name, (perm, poro, aniso) in GEOLOGY.items():
    er.Geom[name].Perm.Type = "Constant"
    er.Geom[name].Perm.Value = perm

er.Perm.TensorType = "TensorByGeom"
er.Geom.Perm.TensorByGeom.Names = "domain " + " ".join(n for n, (_, _, a) in GEOLOGY.items() if a is not None)
er.Geom.domain.Perm.TensorValX = 1.0
er.Geom.domain.Perm.TensorValY = 1.0
er.Geom.domain.Perm.TensorValZ = 1.0
for name, (_, _, aniso) in GEOLOGY.items():
    if aniso is not None:
        er.Geom[name].Perm.TensorValX = 1.0
        er.Geom[name].Perm.TensorValY = 1.0
        er.Geom[name].Perm.TensorValZ = aniso

er.SpecificStorage.Type = "Constant"
er.SpecificStorage.GeomNames = "domain"
er.Geom.domain.SpecificStorage.Value = 1.0e-4

er.Geom.Porosity.GeomNames = "domain " + " ".join(list(SOILS) + list(GEOLOGY))
er.Geom.domain.Porosity.Type = "Constant"
er.Geom.domain.Porosity.Value = 0.33
for name, (_, poro, *_rest) in {**SOILS, **GEOLOGY}.items():
    er.Geom[name].Porosity.Type = "Constant"
    er.Geom[name].Porosity.Value = poro

# van Genuchten curves, evaluated from lookup tables (100,000 points, linear) for speed
er.Phase.RelPerm.Type = "VanGenuchten"
er.Phase.RelPerm.GeomNames = "domain " + " ".join(SOILS)
er.Phase.Saturation.Type = "VanGenuchten"
er.Phase.Saturation.GeomNames = "domain " + " ".join(SOILS)
CURVES = {"domain": (0.5, 2.5, 0.0001, -500)}
CURVES.update({name: (alpha, n, sres, -300) for name, (_, _, alpha, n, sres) in SOILS.items()})
for name, (alpha, n, sres, pmin) in CURVES.items():
    for kind in ("RelPerm", "Saturation"):
        er.Geom[name][kind].Alpha = alpha
        er.Geom[name][kind].N = n
        er.Geom[name][kind].InterpolationMethod = "Linear"
        er.Geom[name][kind].NumSamplePoints = 100000
        er.Geom[name][kind].MinPressureHead = pmin
    er.Geom[name].Saturation.SRes = sres
    er.Geom[name].Saturation.SSat = 1.0

# a vertical flow barrier (multiplies the flux across the face above each cell): the
# CONUS2.1 soil-bedrock interface, from the static inputs
er.Solver.Nonlinear.FlowBarrierZ = True
er.FBz.Type = "PFBFile"
er.Geom.domain.FBz.FileName = "pf_flowbarrier.pfb"

# ---------------------------------------------------------------- water, sources, wells
er.Phase.Names = "water"
er.Phase.water.Density.Type = "Constant"
er.Phase.water.Density.Value = 1.0
er.Phase.water.Viscosity.Type = "Constant"
er.Phase.water.Viscosity.Value = 1.0
er.Phase.water.Mobility.Type = "Constant"
er.Phase.water.Mobility.Value = 1.0
er.Gravity = 1.0
er.Contaminants.Names = ""
er.Geom.Retardation.GeomNames = ""
er.Wells.Names = ""
er.PhaseSources.water.Type = "Constant"
er.PhaseSources.water.GeomNames = "domain"
er.PhaseSources.water.Geom.domain.Value = 0.0
er.KnownSolution = "NoKnownSolution"

# ---------------------------------------------------------------- topography and overland flow
er.Solver.TerrainFollowingGrid = True
er.Solver.TerrainFollowingGrid.SlopeUpwindFormulation = "Upwind"
er.TopoSlopesX.Type = "PFBFile"
er.TopoSlopesX.GeomNames = "domain"
er.TopoSlopesX.FileName = "slope_x.pfb"
er.TopoSlopesY.Type = "PFBFile"
er.TopoSlopesY.GeomNames = "domain"
er.TopoSlopesY.FileName = "slope_y.pfb"
er.Mannings.Type = "PFBFile"
er.Mannings.GeomNames = "domain"
er.Mannings.FileName = "mannings.pfb"     # drainage-network scheme: channels 0.12, hillslopes 0.045 (hr m^-1/3 scaled)

# ---------------------------------------------------------------- boundary conditions
er.Cycle.Names = "constant"
er.Cycle.constant.Names = "alltime"
er.Cycle.constant.alltime.Length = 1
er.Cycle.constant.Repeat = -1
er.BCPressure.PatchNames = "top bottom side"
er.Patch.top.BCPressure.Type = "OverlandKinematic"
er.Patch.top.BCPressure.Cycle = "constant"
er.Patch.top.BCPressure.alltime.Value = 0.0
er.Patch.bottom.BCPressure.Type = "FluxConst"
er.Patch.bottom.BCPressure.Cycle = "constant"
er.Patch.bottom.BCPressure.alltime.Value = 0.0
er.Patch.side.BCPressure.Type = "FluxConst"
er.Patch.side.BCPressure.Cycle = "constant"
er.Patch.side.BCPressure.alltime.Value = 0.0

# ---------------------------------------------------------------- initial condition
# the spun-up pressure field (a cyclic WY2017 coupled spin-up) and the matching CLM restart
er.ICPressure.Type = "PFBFile"
er.ICPressure.GeomNames = "domain"
er.Geom.domain.ICPressure.FileName = "ic_pressure.pfb"
er.Geom.domain.ICPressure.RefPatch = "bottom"

# ---------------------------------------------------------------- timing
er.TimingInfo.BaseUnit = 1.0
er.TimingInfo.StartCount = 0
er.TimingInfo.StartTime = 0.0
er.TimingInfo.StopTime = float(args.hours)
er.TimingInfo.DumpInterval = 1.0           # hourly output
er.TimeStep.Type = "Constant"
er.TimeStep.Value = 1.0                    # one hour

# ---------------------------------------------------------------- CLM (land surface)
er.Solver.LSM = "CLM"
er.Solver.CLM.MetForcing = "3D"
er.Solver.CLM.MetFileName = "CW3E"
er.Solver.CLM.MetFilePath = os.path.abspath(args.forcing)
er.Solver.CLM.MetFileNT = 24               # one file per day
er.Solver.CLM.IstepStart = 1
er.Solver.CLM.ReuseCount = 1
er.Solver.CLM.SingleFile = True
er.Solver.CLM.CLMDumpInterval = 1
er.Solver.CLM.DailyRST = True
er.Solver.CLM.WriteLastRST = True
er.Solver.CLM.WriteLogs = False
er.Solver.CLM.Print1dOut = False
er.Solver.CLM.IrrigationType = "none"
er.Solver.CLM.RootZoneNZ = 5               # CLM's root zone spans the top five ParFlow layers
er.Solver.CLM.SoiLayer = 3
er.Solver.CLM.ResSat = 0.2
er.Solver.CLM.RZWaterStress = 2
er.Solver.CLM.VegWaterStress = "Saturation"
er.Solver.CLM.WiltingPoint = 0.2
er.Solver.CLM.FieldCapacity = 1.0
er.Solver.CLM.EvapBeta = "Linear"
# the calibrated snow and canopy physics (ParFlow >= 3.15)
er.Solver.CLM.StomataScheme = "Medlyn"
er.Solver.CLM.InterceptionScheme = "CLM5Tanh"
er.Solver.CLM.InterceptionTanhAlpha = 1.0
er.Solver.CLM.FracSnoScheme = "SZA"        # snow-cover fraction with a solar-zenith-angle term
er.Solver.CLM.FracSnoGammaSZA = 4.0
er.Solver.CLM.FracSnoAvgWindow = 72.0
er.Solver.CLM.FracSnoRoughnessMin = 1.0e-8
er.Solver.CLM.FracSnoRoughnessMax = 0.2

# ---------------------------------------------------------------- solver
# Newton-Krylov (KINSOL) with the settings that ran fastest on this case: the preconditioner
# built from the symmetric part of the Jacobian (halves the linear iterations), a constant
# forcing term of 0.01, and the surface ponding predictor.  See README.md, Solver configuration.
er.Solver = "Richards"
er.Solver.MaxConvergenceFailures = 5
er.Solver.Nonlinear.MaxIter = 250
er.Solver.Nonlinear.ResidualTol = 1.0e-6
er.Solver.Nonlinear.StepTol = 1.0e-15
er.Solver.Nonlinear.EtaChoice = "EtaConstant"
er.Solver.Nonlinear.EtaValue = 0.01
er.Solver.Nonlinear.UseJacobian = True
er.Solver.Nonlinear.Globalization = "LineSearch"
er.Solver.Linear.KrylovDimension = 100
er.Solver.Linear.MaxRestarts = 4
er.Solver.Linear.Preconditioner = "PFMGOctree"
er.Solver.Linear.Preconditioner.PCMatrixType = "PFSymmetric"
er.Solver.SurfacePredictor = True
er.Solver.SurfacePredictor.LateralFlows = True
er.Solver.SurfacePredictor.PressureValue = -1.0

# ---------------------------------------------------------------- output
er.Solver.PrintPressure = True
er.Solver.PrintSaturation = False          # derived from pressure; turn on if you want it
er.Solver.PrintEvapTrans = True            # CLM's flux into ParFlow, per cell
er.Solver.PrintCLM = True                  # SWE, ET components, soil temperature, etc.
er.Solver.WriteCLMBinary = False
er.Solver.PrintSubsurfData = True
er.Solver.PrintSlopes = True
er.Solver.PrintMannings = True
er.Solver.PrintMask = True
er.Solver.PrintTop = True
if args.netcdf:
    er.NetCDF.NumStepsPerFile = 24
    er.NetCDF.WritePressure = True
    er.NetCDF.WriteSaturation = True
    er.NetCDF.WriteCLM = True
    er.NetCDF.EvapTrans = True

# ---------------------------------------------------------------- distribute inputs and run
for f in ("pf_indicator.pfb", "slope_x.pfb", "slope_y.pfb", "mannings.pfb", "pf_flowbarrier.pfb", "ic_pressure.pfb"):
    er.dist(f)
er.run()
