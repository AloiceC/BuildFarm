param(
    [Parameter(Mandatory = $true)][string]$Repository,
    [Parameter(Mandatory = $true)][string]$HandoffRef,
    [string]$RequestedSha = '',
    [Parameter(Mandatory = $true)][string]$Token,
    [Parameter(Mandatory = $true)][string]$OutputFile
)

$ErrorActionPreference = 'Stop'
$apiVersion = '2026-03-10'
$headers = @{
    Accept = 'application/vnd.github+json'
    Authorization = "Bearer $Token"
    'X-GitHub-Api-Version' = $apiVersion
}

if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    throw 'Invalid repository.'
}
if ($HandoffRef -ne 'ci/buildfarm') {
    throw 'Private v1 requires ci/buildfarm handoff.'
}

if ([string]::IsNullOrWhiteSpace($RequestedSha)) {
    $encodedRef = [uri]::EscapeDataString("heads/$HandoffRef")
    $refUri = "https://api.github.com/repos/$Repository/git/ref/$encodedRef"
    $ref = Invoke-RestMethod -Method Get -Uri $refUri -Headers $headers
    $sha = [string]$ref.object.sha
} else {
    if ($RequestedSha -notmatch '^[0-9a-fA-F]{40}$') {
        throw 'commit_sha must be an exact 40-character SHA.'
    }
    $commitUri = "https://api.github.com/repos/$Repository/commits/$RequestedSha"
    $commit = Invoke-RestMethod -Method Get -Uri $commitUri -Headers $headers
    $sha = [string]$commit.sha
}

if ($sha -notmatch '^[0-9a-f]{40}$') {
    throw 'GitHub did not return an exact commit SHA.'
}

$workRoot = Join-Path $env:RUNNER_TEMP "private-source-$sha"
$zipPath = Join-Path $env:RUNNER_TEMP "private-source-$sha.zip"
if (Test-Path -LiteralPath $workRoot) { Remove-Item -LiteralPath $workRoot -Recurse -Force }
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
New-Item -ItemType Directory -Path $workRoot | Out-Null

$archiveUri = "https://api.github.com/repos/$Repository/zipball/$sha"
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
try {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $archiveUri)
    $request.Headers.Accept.ParseAdd('application/vnd.github+json')
    $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token)
    $request.Headers.Add('X-GitHub-Api-Version', $apiVersion)
    $response = $client.SendAsync($request).GetAwaiter().GetResult()
    if ([int]$response.StatusCode -notin 302, 301, 307, 308) {
        throw "Archive request failed with HTTP $([int]$response.StatusCode)."
    }
    $downloadUri = $response.Headers.Location
    if ($null -eq $downloadUri -or $downloadUri.Scheme -ne 'https') {
        throw 'GitHub archive redirect was missing or not HTTPS.'
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}

$downloadClient = [System.Net.Http.HttpClient]::new()
try {
    $stream = $downloadClient.GetStreamAsync($downloadUri).GetAwaiter().GetResult()
    try {
        $file = [System.IO.File]::Create($zipPath)
        try { $stream.CopyTo($file) } finally { $file.Dispose() }
    } finally {
        $stream.Dispose()
    }
} finally {
    $downloadClient.Dispose()
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $workRoot -Force
Remove-Item -LiteralPath $zipPath -Force

$roots = @(Get-ChildItem -LiteralPath $workRoot -Directory)
if ($roots.Count -ne 1) {
    throw 'Unexpected GitHub archive layout.'
}
$sourceDir = $roots[0].FullName

"sha=$sha" | Add-Content -LiteralPath $OutputFile -Encoding utf8
"source_dir=$sourceDir" | Add-Content -LiteralPath $OutputFile -Encoding utf8
Write-Host "Private source archive acquired for SHA $sha."
