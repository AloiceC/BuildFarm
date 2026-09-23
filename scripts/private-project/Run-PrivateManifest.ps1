param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$ResultPath,
    [Parameter(Mandatory = $true)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'

function Get-SanitizedDiagnostic {
    param(
        [string]$StdOutPath,
        [string]$StdErrPath,
        [string]$SourceRoot
    )

    $lines = @()
    foreach ($path in @($StdErrPath, $StdOutPath)) {
        if (Test-Path -LiteralPath $path) {
            $lines += Get-Content -LiteralPath $path -ErrorAction SilentlyContinue
        }
    }

    $clean = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        $text = [regex]::Replace([string]$line, "`e\[[0-9;?]*[ -/]*[@-~]", '')
        $text = $text.Replace($SourceRoot, '<source>')
        if ($env:RUNNER_TEMP) { $text = $text.Replace($env:RUNNER_TEMP, '<temp>') }
        $text = [regex]::Replace($text, '(?i)Authorization:\s*(Bearer\s+)?\S+', 'Authorization: <redacted>')
        $text = [regex]::Replace($text, '(?i)\bBearer\s+[A-Za-z0-9._-]+', 'Bearer <redacted>')
        $text = [regex]::Replace($text, '\bgh[opsu]_[A-Za-z0-9_]{16,}\b', '<redacted-token>')
        $text = [regex]::Replace($text, '\bgithub_pat_[A-Za-z0-9_]{16,}\b', '<redacted-token>')

        if ($text -match '^\s*\d+\s*\|') { continue }
        if ($text -match '^\s*\|\s*[\^~_-]+\s*$') { continue }
        if ($text -match '^\s*[> ]*\d+\s+\|') { continue }

        if (-not [string]::IsNullOrWhiteSpace($text)) {
            $clean.Add($text)
        }
        if ($clean.Count -ge 120) { break }
    }

    $joined = ($clean -join "`n")
    if ($joined.Length -gt 12000) {
        $joined = $joined.Substring(0, 12000) + "`n<diagnostic truncated>"
    }
    return $joined
}

$sourceRoot = [System.IO.Path]::GetFullPath($SourceDir)
$manifestFull = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot $ManifestPath))
$manifest = Get-Content -LiteralPath $manifestFull -Raw | ConvertFrom-Json

$result = [ordered]@{
    schema_version = 1
    project_id = [string]$manifest.project_id
    overall = 'success'
    stages = @()
}

$stageIndex = 0
foreach ($stage in @($manifest.stages)) {
    $stageIndex++
    $id = [string]$stage.id
    $label = [string]$stage.label
    $command = [string]$stage.command
    if ([string]::IsNullOrWhiteSpace($id) -or [string]::IsNullOrWhiteSpace($command)) {
        throw 'Each private stage requires id and command.'
    }

    $scriptPath = Join-Path $env:RUNNER_TEMP ("private-stage-{0:D2}.ps1" -f $stageIndex)
    $stdoutPath = Join-Path $env:RUNNER_TEMP ("private-stage-{0:D2}.stdout.log" -f $stageIndex)
    $stderrPath = Join-Path $env:RUNNER_TEMP ("private-stage-{0:D2}.stderr.log" -f $stageIndex)
    Set-Content -LiteralPath $scriptPath -Value $command -Encoding utf8

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath 'pwsh' `
        -ArgumentList @('-NoLogo', '-NoProfile', '-NonInteractive', '-File', $scriptPath) `
        -WorkingDirectory $sourceRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -Wait -PassThru
    $stopwatch.Stop()

    $status = if ($process.ExitCode -eq 0) { 'success' } else { 'failure' }
    $diagnostic = ''
    if ($status -eq 'failure') {
        $diagnostic = Get-SanitizedDiagnostic -StdOutPath $stdoutPath -StdErrPath $stderrPath -SourceRoot $sourceRoot
        $result.overall = 'failure'
    }

    $result.stages += [ordered]@{
        id = $id
        label = $label
        status = $status
        duration_seconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
        exit_code = $process.ExitCode
        diagnostic = $diagnostic
    }

    $publicLabel = if ([string]::IsNullOrWhiteSpace($label)) { $id } else { $label }
    Write-Host ("Stage {0}: {1} ({2:N2}s)" -f $publicLabel, $status.ToUpperInvariant(), $stopwatch.Elapsed.TotalSeconds)

    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue

    if ($status -eq 'failure') {
        break
    }
}

$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ResultPath -Encoding utf8
"result=$($result.overall)" | Add-Content -LiteralPath $OutputFile -Encoding utf8
