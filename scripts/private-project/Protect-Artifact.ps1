param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$CommitSha,
    [Parameter(Mandatory = $true)][string]$Recipient,
    [Parameter(Mandatory = $true)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Recipient) -or $Recipient -notmatch '^age1') {
    throw 'AGE_RECIPIENT is missing or invalid.'
}

$sourceRoot = [System.IO.Path]::GetFullPath($SourceDir)
$manifestFull = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot $ManifestPath))
$manifest = Get-Content -LiteralPath $manifestFull -Raw | ConvertFrom-Json
if ($null -eq $manifest.delivery -or @($manifest.delivery.paths).Count -eq 0) {
    throw 'Private manifest does not define delivery paths.'
}

$stageDir = Join-Path $env:RUNNER_TEMP "delivery-$CommitSha"
$zipPath = Join-Path $env:RUNNER_TEMP "delivery-$CommitSha.zip"
$encryptedPath = Join-Path $env:RUNNER_TEMP "delivery-$CommitSha.zip.age"
Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath, $encryptedPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stageDir | Out-Null

foreach ($relative in @($manifest.delivery.paths)) {
    $full = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot ([string]$relative)))
    if (-not $full.StartsWith($sourceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Delivery path escapes source directory.'
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw 'A required delivery file was not produced.'
    }
    Copy-Item -LiteralPath $full -Destination (Join-Path $stageDir ([System.IO.Path]::GetFileName($full)))
}

Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -CompressionLevel Optimal

$ageVersion = '1.3.2'
$ageUrl = "https://github.com/FiloSottile/age/releases/download/v$ageVersion/age-v$ageVersion-windows-amd64.zip"
$ageSha256 = 'f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7'
$ageZip = Join-Path $env:RUNNER_TEMP "age-v$ageVersion-windows-amd64.zip"
$ageDir = Join-Path $env:RUNNER_TEMP "age-v$ageVersion"
Remove-Item -LiteralPath $ageZip -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ageDir -Recurse -Force -ErrorAction SilentlyContinue

Invoke-WebRequest -Uri $ageUrl -OutFile $ageZip
$actual = (Get-FileHash -LiteralPath $ageZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $ageSha256) {
    throw 'age release archive checksum mismatch.'
}
Expand-Archive -LiteralPath $ageZip -DestinationPath $ageDir -Force
$ageExe = Get-ChildItem -LiteralPath $ageDir -Filter 'age.exe' -Recurse | Select-Object -First 1
if ($null -eq $ageExe) { throw 'age.exe not found in verified archive.' }

$ageStdOut = Join-Path $env:RUNNER_TEMP 'age.stdout.log'
$ageStdErr = Join-Path $env:RUNNER_TEMP 'age.stderr.log'
$process = Start-Process -FilePath $ageExe.FullName `
    -ArgumentList @('-r', $Recipient, '-o', $encryptedPath, $zipPath) `
    -RedirectStandardOutput $ageStdOut `
    -RedirectStandardError $ageStdErr `
    -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $encryptedPath -PathType Leaf)) {
    throw 'age encryption failed.'
}

Remove-Item -LiteralPath $zipPath -Force
Remove-Item -LiteralPath $stageDir -Recurse -Force
Remove-Item -LiteralPath $ageZip -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ageDir -Recurse -Force -ErrorAction SilentlyContinue

$baseName = [string]$manifest.delivery.artifact_basename
if ([string]::IsNullOrWhiteSpace($baseName)) { $baseName = $manifest.project_id }
$artifactName = "$baseName-$($CommitSha.Substring(0,12))-age"

"encrypted_path=$encryptedPath" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"artifact_name=$artifactName" | Add-Content -LiteralPath $OutputFile -Encoding utf8
Write-Host 'Encrypted acceptance package prepared.'
