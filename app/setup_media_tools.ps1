[CmdletBinding()]
param(
    [switch] $Check,
    [switch] $Install
)

$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsRoot = Join-Path $appRoot '.tools'
$ffmpegExe = Join-Path $toolsRoot 'ffmpeg\bin\ffmpeg.exe'
$mediamtxExe = Join-Path $toolsRoot 'mediamtx\mediamtx.exe'
$ffmpegVersion = '9.0.2'
$mediamtxVersion = '1.21.1'
$ffmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
$ffmpegSha256 = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
$mediamtxArchive = "mediamtx_v${mediamtxVersion}_windows_amd64.zip"
$mediamtxUrl = "https://github.com/bluenviron/mediamtx/releases/download/v${mediamtxVersion}/${mediamtxArchive}"
$mediamtxChecksumsUrl = "https://github.com/bluenviron/mediamtx/releases/download/v${mediamtxVersion}/checksums.sha256"

function Test-PinnedTools {
    if (-not (Test-Path -LiteralPath $ffmpegExe) -or -not (Test-Path -LiteralPath $mediamtxExe)) { return $false }
    $ffmpegLine = (& $ffmpegExe -version 2>&1 | Select-Object -First 1) -join ''
    $mediamtxLine = (& $mediamtxExe --version 2>&1 | Select-Object -First 1) -join ''
    return ($ffmpegLine -match [regex]::Escape("ffmpeg version $ffmpegVersion-essentials_build")) -and ($mediamtxLine -match [regex]::Escape("v$mediamtxVersion"))
}

if ($Check) {
    if (Test-PinnedTools) {
        Write-Host "FFmpeg $ffmpegVersion and MediaMTX $mediamtxVersion are installed under .tools."
        exit 0
    }
    Write-Host 'Pinned media tools are missing or have a different version.'
    exit 1
}

if (-not $Install) { throw 'Use -Check or -Install.' }

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("netsim-media-tools-{0}" -f ([guid]::NewGuid().ToString('N')))
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $ffmpegZip = Join-Path $tempRoot 'ffmpeg.zip'
    $mediamtxZip = Join-Path $tempRoot $mediamtxArchive
    $checksums = Join-Path $tempRoot 'checksums.sha256'

    Write-Host "Downloading FFmpeg $ffmpegVersion Essentials..."
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip -UseBasicParsing
    $actualFfmpegHash = (Get-FileHash -LiteralPath $ffmpegZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualFfmpegHash -ne $ffmpegSha256) { throw "FFmpeg checksum mismatch. Expected $ffmpegSha256, received $actualFfmpegHash." }
    $ffmpegExtract = Join-Path $tempRoot 'ffmpeg'
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtract -Force
    $ffmpegBinary = Get-ChildItem -LiteralPath $ffmpegExtract -Filter 'ffmpeg.exe' -Recurse -File | Select-Object -First 1
    if (-not $ffmpegBinary) { throw 'The FFmpeg archive did not contain ffmpeg.exe.' }
    $ffmpegPackageRoot = $ffmpegBinary.Directory.Parent.FullName
    Remove-Item -LiteralPath (Join-Path $toolsRoot 'ffmpeg') -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path (Join-Path $toolsRoot 'ffmpeg') -Force | Out-Null
    Copy-Item -Path (Join-Path $ffmpegPackageRoot '*') -Destination (Join-Path $toolsRoot 'ffmpeg') -Recurse -Force

    Write-Host "Downloading MediaMTX $mediamtxVersion..."
    Invoke-WebRequest -Uri $mediamtxUrl -OutFile $mediamtxZip -UseBasicParsing
    Invoke-WebRequest -Uri $mediamtxChecksumsUrl -OutFile $checksums -UseBasicParsing
    $checksumLine = Get-Content -LiteralPath $checksums | Where-Object { $_ -match [regex]::Escape($mediamtxArchive) } | Select-Object -First 1
    if (-not $checksumLine) { throw "MediaMTX checksum for $mediamtxArchive was not found." }
    $expectedMediaMtxHash = ($checksumLine -split '\s+')[0].ToLowerInvariant()
    $actualMediaMtxHash = (Get-FileHash -LiteralPath $mediamtxZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualMediaMtxHash -ne $expectedMediaMtxHash) { throw "MediaMTX checksum mismatch. Expected $expectedMediaMtxHash, received $actualMediaMtxHash." }
    $mediamtxExtract = Join-Path $tempRoot 'mediamtx'
    Expand-Archive -LiteralPath $mediamtxZip -DestinationPath $mediamtxExtract -Force
    $mediamtxBinary = Get-ChildItem -LiteralPath $mediamtxExtract -Filter 'mediamtx.exe' -Recurse -File | Select-Object -First 1
    if (-not $mediamtxBinary) { throw 'The MediaMTX archive did not contain mediamtx.exe.' }
    Remove-Item -LiteralPath (Join-Path $toolsRoot 'mediamtx') -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path (Join-Path $toolsRoot 'mediamtx') -Force | Out-Null
    Copy-Item -LiteralPath $mediamtxBinary.FullName -Destination (Join-Path $toolsRoot 'mediamtx\mediamtx.exe') -Force

    if (-not (Test-PinnedTools)) { throw 'The downloaded tools did not pass the version check after extraction.' }
    Write-Host "Installed FFmpeg $ffmpegVersion and MediaMTX $mediamtxVersion under .tools."
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
