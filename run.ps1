$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
if (-not $env:PORT) { $env:PORT = '8000' }
if (-not $env:HOST) { $env:HOST = '127.0.0.1' }
python -m cause_ai
