param(
  [Alias("Host")]
  [string]$BindHost = "0.0.0.0",
  [int]$Port = 8080,
  [string]$DataDir = "",
  [string]$EnvFile = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $EnvFile) {
  $EnvFile = Join-Path $ProjectDir ".gateway.env"
}

function Import-GatewayEnv {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    return
  }
  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
      continue
    }
    $separator = $line.IndexOf("=")
    if ($separator -le 0) {
      continue
    }
    $key = $line.Substring(0, $separator).Trim()
    $value = $line.Substring($separator + 1)
    [Environment]::SetEnvironmentVariable($key, $value, "Process")
  }
}

Import-GatewayEnv -Path $EnvFile

$env:PYTHONPATH = Join-Path $ProjectDir "src"
if ($DataDir) {
  $env:GATEWAY_DATA_DIR = $DataDir
} elseif (-not $env:GATEWAY_DATA_DIR) {
  $env:GATEWAY_DATA_DIR = Join-Path $ProjectDir "data"
}

$VenvPython = Join-Path (Join-Path (Join-Path $ProjectDir ".venv") "Scripts") "python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

if ($DryRun) {
  Write-Host "DeepRacer Model Gateway run dry-run"
  Write-Host "Project: $ProjectDir"
  Write-Host "Env file: $EnvFile"
  Write-Host "Python: $Python"
  Write-Host "Data dir: $env:GATEWAY_DATA_DIR"
  Write-Host "User URL: http://$BindHost`:$Port/login"
  Write-Host "Admin URL: http://$BindHost`:$Port/admin/login"
  exit 0
}

& $Python -m uvicorn model_gateway.app:app --host $BindHost --port $Port
