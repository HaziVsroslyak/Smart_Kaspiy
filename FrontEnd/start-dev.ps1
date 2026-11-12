param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5173
)

$ErrorActionPreference = 'Stop'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if ($nodeCommand) {
    $nodeExecutable = $nodeCommand.Source
} else {
    # Optional fallback for this workstation; ordinary Node.js remains preferred.
    $nodeExecutable = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
}
if (-not (Test-Path -LiteralPath $nodeExecutable)) {
    throw 'Node.js was not found. Install Node.js 24 and reopen PowerShell.'
}
$viteEntry = Join-Path $PSScriptRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $viteEntry)) {
    throw 'Frontend dependencies are missing. Run pnpm install in FrontEnd first.'
}

Push-Location $PSScriptRoot
try {
    & $nodeExecutable $viteEntry --host 127.0.0.1 --port $Port --strictPort
    if ($LASTEXITCODE -ne 0) {
        throw "Vite exited with code $LASTEXITCODE. Check the output above."
    }
} finally {
    Pop-Location
}
