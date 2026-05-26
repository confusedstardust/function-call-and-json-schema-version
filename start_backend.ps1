$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$port = if ($env:WEBGAL_PORT) { $env:WEBGAL_PORT } else { "8010" }
python -m uvicorn webgal_backend.app:app --host 127.0.0.1 --port $port
