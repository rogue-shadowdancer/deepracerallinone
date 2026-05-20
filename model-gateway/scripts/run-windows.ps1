$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path (Resolve-Path "$PSScriptRoot\..").Path "src"
if (-not $env:GATEWAY_DATA_DIR) {
  $env:GATEWAY_DATA_DIR = Join-Path (Resolve-Path "$PSScriptRoot\..").Path "data"
}
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
