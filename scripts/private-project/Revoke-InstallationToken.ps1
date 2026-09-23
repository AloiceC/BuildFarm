param([Parameter(Mandatory = $true)][string]$Token)

$ErrorActionPreference = 'Stop'
$headers = @{
    Accept = 'application/vnd.github+json'
    Authorization = "Bearer $Token"
    'X-GitHub-Api-Version' = '2026-03-10'
}

Invoke-WebRequest -Method Delete -Uri 'https://api.github.com/installation/token' -Headers $headers | Out-Null
Write-Host 'Installation token revoked.'
