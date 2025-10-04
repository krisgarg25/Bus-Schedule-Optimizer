param(
  [Parameter(Mandatory=$true)][string]$InputCsv
)

$ErrorActionPreference = "Stop"

# Defaults (override as needed)
$env:OPT_SCHEDULE = $env:OPT_SCHEDULE -as [string]
if (-not $env:OPT_SCHEDULE) { $env:OPT_SCHEDULE = "schedule.csv" }

$env:OPT_CAPACITY = $env:OPT_CAPACITY -as [string]
if (-not $env:OPT_CAPACITY) { $env:OPT_CAPACITY = "45" }

$env:OPT_SHIFT_OPTIONS = $env:OPT_SHIFT_OPTIONS -as [string]
if (-not $env:OPT_SHIFT_OPTIONS) { $env:OPT_SHIFT_OPTIONS = "-15 0 15" }

$env:OPT_MAX_ADD_PER_DEP = $env:OPT_MAX_ADD_PER_DEP -as [string]
if (-not $env:OPT_MAX_ADD_PER_DEP) { $env:OPT_MAX_ADD_PER_DEP = "2" }

$env:OPT_UNMET_PENALTY = $env:OPT_UNMET_PENALTY -as [string]
if (-not $env:OPT_UNMET_PENALTY) { $env:OPT_UNMET_PENALTY = "10.0" }

$env:OPT_OPERATING_COST = $env:OPT_OPERATING_COST -as [string]
if (-not $env:OPT_OPERATING_COST) { $env:OPT_OPERATING_COST = "3.0" }

$env:OPT_ADD_BUS_COST = $env:OPT_ADD_BUS_COST -as [string]
if (-not $env:OPT_ADD_BUS_COST) { $env:OPT_ADD_BUS_COST = "120.0" }

$env:OPT_PLAN_CSV = $env:OPT_PLAN_CSV -as [string]
if (-not $env:OPT_PLAN_CSV) { $env:OPT_PLAN_CSV = "plan.csv" }

python optimize.py -i $InputCsv

