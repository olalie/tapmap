# Clean build artifacts.
# Run from project root:
#     powershell -ExecutionPolicy Bypass -File tools/clean.ps1

$root = Split-Path -Parent $PSScriptRoot

Remove-Item -Recurse -Force `
    "$root\build",
    "$root\dist",
    "$root\__pycache__",
    "$root\.ruff_cache",
    "$root\.pytest_cache" `
    -ErrorAction SilentlyContinue
    
Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $root -Recurse -Filter "*.pyc" |
    Remove-Item -Force -ErrorAction SilentlyContinue
