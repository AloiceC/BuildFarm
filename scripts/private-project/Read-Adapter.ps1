param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'

if ($Project -notmatch '^[a-z0-9][a-z0-9-]*$') {
    throw 'Invalid project adapter id.'
}

$adapterPath = Join-Path $PSScriptRoot "..\..\projects\$Project\adapter.json"
$adapterPath = [System.IO.Path]::GetFullPath($adapterPath)
if (-not (Test-Path -LiteralPath $adapterPath -PathType Leaf)) {
    throw 'Project adapter not found.'
}

$adapter = Get-Content -LiteralPath $adapterPath -Raw | ConvertFrom-Json
if ($adapter.schema_version -ne 1) { throw 'Unsupported adapter schema.' }
if ($adapter.project_id -ne $Project) { throw 'Adapter project id mismatch.' }
if ($adapter.handoff_ref -ne 'ci/buildfarm') { throw 'Private v1 requires ci/buildfarm handoff.' }
if ($adapter.source_repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    throw 'Invalid source repository.'
}
if ([string]::IsNullOrWhiteSpace($adapter.project_manifest)) {
    throw 'Project manifest path is required.'
}

$parts = $adapter.source_repository.Split('/', 2)
"repository=$($adapter.source_repository)" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"owner=$($parts[0])" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"repository_name=$($parts[1])" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"handoff_ref=$($adapter.handoff_ref)" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"project_manifest=$($adapter.project_manifest)" | Add-Content -LiteralPath $OutputFile -Encoding utf8

Write-Host "Adapter $Project loaded."
