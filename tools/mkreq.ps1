# Generate requirements.txt using pipreqs.
# Run from project root:
#     powershell -ExecutionPolicy Bypass -File tools/mkreq.ps1

$root = Split-Path -Parent $PSScriptRoot

Set-Location $root

pipreqs . --force --encoding utf-8 `
  --ignore ".venv,venv,dist,build,docs,tests,tools"

Write-Host "requirements.txt generated in $root"
