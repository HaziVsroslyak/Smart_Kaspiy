param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$pythonExecutable = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Project virtual environment is missing. Create .venv and install Backend/requirements.txt first.'
}
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    throw "Port $Port is already in use (PID: $($existing.OwningProcess -join ', ')). Stop the old backend terminal before launching this script."
}
Push-Location $PSScriptRoot
try {
    & $pythonExecutable -m uvicorn main:app --app-dir $PSScriptRoot --host 127.0.0.1 --port $Port --reload --reload-dir $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
