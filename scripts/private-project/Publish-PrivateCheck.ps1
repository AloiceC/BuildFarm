param(
    [Parameter(Mandatory = $true)][string]$Repository,
    [Parameter(Mandatory = $true)][string]$CommitSha,
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$ResultPath,
    [Parameter(Mandatory = $true)][string]$Token,
    [bool]$DeliveryRequested = $false,
    [bool]$DeliverySucceeded = $false
)

$ErrorActionPreference = 'Stop'

if ($CommitSha -notmatch '^[0-9a-f]{40}$') { throw 'Invalid exact commit SHA.' }

if (Test-Path -LiteralPath $ResultPath) {
    $result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
} else {
    $result = [pscustomobject]@{
        overall = 'failure'
        stages = @()
    }
}

$summaryLines = New-Object System.Collections.Generic.List[string]
$summaryLines.Add("BuildFarm v1 validation for ``$Project``.")
$summaryLines.Add('')
$summaryLines.Add('| Stage | Result | Duration |')
$summaryLines.Add('| --- | --- | ---: |')
foreach ($stage in @($result.stages)) {
    $duration = "{0:N2}s" -f [double]$stage.duration_seconds
    $summaryLines.Add("| $($stage.label) | $($stage.status.ToUpperInvariant()) | $duration |")
}
if ($DeliveryRequested) {
    $delivery = if ($DeliverySucceeded) { 'PASS' } else { 'FAIL' }
    $summaryLines.Add('')
    $summaryLines.Add("Encrypted acceptance delivery: **$delivery**")
}

$detailBlocks = New-Object System.Collections.Generic.List[string]
foreach ($stage in @($result.stages)) {
    if ($stage.status -eq 'failure' -and -not [string]::IsNullOrWhiteSpace([string]$stage.diagnostic)) {
        $detailBlocks.Add("### $($stage.label)`n```text`n$($stage.diagnostic)`n```")
    }
}
$text = ($detailBlocks -join "`n`n")
if ($text.Length -gt 50000) {
    $text = $text.Substring(0, 50000) + "`n<check output truncated>"
}

$conclusion = if ($result.overall -eq 'success' -and (-not $DeliveryRequested -or $DeliverySucceeded)) {
    'success'
} else {
    'failure'
}

$body = @{
    name = "BuildFarm v1 / $Project"
    head_sha = $CommitSha
    status = 'completed'
    conclusion = $conclusion
    external_id = "buildfarm-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
    details_url = "$env:GITHUB_SERVER_URL/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID"
    output = @{
        title = if ($conclusion -eq 'success') { 'BuildFarm validation passed' } else { 'BuildFarm validation failed' }
        summary = ($summaryLines -join "`n")
        text = $text
    }
} | ConvertTo-Json -Depth 8

$headers = @{
    Accept = 'application/vnd.github+json'
    Authorization = "Bearer $Token"
    'X-GitHub-Api-Version' = '2026-03-10'
}
Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repository/check-runs" -Headers $headers -ContentType 'application/json' -Body $body | Out-Null
Write-Host 'Private Check Run published.'
