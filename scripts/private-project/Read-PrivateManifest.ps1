param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$ExpectedProject,
    [Parameter(Mandatory = $true)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'
$sourceRoot = [System.IO.Path]::GetFullPath($SourceDir)
$manifestFull = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot $ManifestPath))
if (-not $manifestFull.StartsWith($sourceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Manifest path escapes source directory.'
}
if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) {
    throw 'Private build manifest not found.'
}

$manifest = Get-Content -LiteralPath $manifestFull -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1) { throw 'Unsupported private manifest schema.' }
if ($manifest.project_id -ne $ExpectedProject) { throw 'Private manifest project id mismatch.' }
if ($null -eq $manifest.stages -or @($manifest.stages).Count -eq 0) {
    throw 'Private manifest must define at least one stage.'
}

$nodeVersion = ''
if ($null -ne $manifest.toolchains -and $null -ne $manifest.toolchains.node) {
    $nodeVersion = [string]$manifest.toolchains.node
}
"node_version=$nodeVersion" | Add-Content -LiteralPath $OutputFile -Encoding utf8
Write-Host 'Private build manifest accepted.'
