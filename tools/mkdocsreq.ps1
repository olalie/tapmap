# Generate docs-requirements.txt with MkDocs packages.
# Run from project root:
#     powershell -ExecutionPolicy Bypass -File tools/mkdocsreq.ps1

$root = Split-Path -Parent $PSScriptRoot

Set-Location $root

pip freeze | Select-String '^mkdocs' | ForEach-Object { $_.Line } | Set-Content docs-requirements.txt

Write-Host "docs-requirements.txt generated in $root"
