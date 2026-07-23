# Sign a single executable using SignPath.
#
# This script is used:
#   - directly by build_windows.py to sign TapMap.exe
#   - by Inno Setup to sign the generated uninstaller and installer
#
# Required environment variable:
#   SIGNPATH_API_TOKEN
#
# If the SignPath PowerShell module is missing, it is installed
# automatically for the current user.

param(
    [Parameter(Mandatory = $true)]
    [string]$File
)

$ErrorActionPreference = "Stop"

# SignPath project configuration.
$organizationId = "95d3450c-5444-470c-a16f-9e990aacf813"
$projectSlug = "tapmap"
$signingPolicy = "test-signing"
$apiToken = $env:SIGNPATH_API_TOKEN

if ([string]::IsNullOrWhiteSpace($apiToken)) {
    throw "SIGNPATH_API_TOKEN environment variable is not set."
}

Write-Host "Signing: $File"

try {

    if (-not (Get-Module -ListAvailable SignPath)) {
        Write-Host "Installing SignPath PowerShell module..."
        Install-Module SignPath `
            -Scope CurrentUser `
            -Force `
            -AllowClobber
    }

    Import-Module SignPath -ErrorAction Stop

    Submit-SigningRequest `
        -ApiToken $apiToken `
        -OrganizationId $organizationId `
        -ProjectSlug $projectSlug `
        -SigningPolicySlug $signingPolicy `
        -InputArtifactPath $File `
        -WaitForCompletion `
        -OutputArtifactPath $File `
        -Force

    Write-Host "Signing completed."
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
