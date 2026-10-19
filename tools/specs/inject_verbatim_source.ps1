# Inject a verbatim source document into a spec.md between fixed markers.
# The source is copied byte-for-byte (no trimming, no normalisation).
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SpecPath,
    [Parameter(Mandatory = $true)][string]$SourcePath
)

$ErrorActionPreference = 'Stop'

$beginMarker = '<!-- BEGIN VERBATIM SOURCE -->'
$endMarker = '<!-- END VERBATIM SOURCE -->'

$fence = [string][char]96 + [string][char]96 + [string][char]96
$newline = "`n"

$specRaw = [System.IO.File]::ReadAllText($SpecPath)
$sourceRaw = [System.IO.File]::ReadAllText($SourcePath)

$beginIndex = $specRaw.IndexOf($beginMarker)
$endIndex = $specRaw.IndexOf($endMarker)
if ($beginIndex -lt 0 -or $endIndex -lt 0 -or $endIndex -lt $beginIndex) {
    throw "Verbatim markers not found (or out of order) in $SpecPath"
}

$headLength = $beginIndex + $beginMarker.Length
$head = $specRaw.Substring(0, $headLength)
$tail = $specRaw.Substring($endIndex)

# Block: newline, opening fence with language, source exactly as-is, newline, closing fence, newline.
$block = $newline + $fence + 'markdown' + $newline + $sourceRaw + $newline + $fence + $newline

$updated = $head + $block + $tail
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($SpecPath, $updated, $utf8NoBom)

# ---- verification -----------------------------------------------------------
$checkRaw = [System.IO.File]::ReadAllText($SpecPath)
$s = $checkRaw.IndexOf($beginMarker) + $beginMarker.Length
$e = $checkRaw.IndexOf($endMarker)
$body = $checkRaw.Substring($s, $e - $s).Trim("`r", "`n")
$openPattern = '(?s)^' + [regex]::Escape($fence) + 'markdown\r?\n'
$closePattern = '\r?\n' + [regex]::Escape($fence) + '$'
$text = ($body -replace $openPattern, '') -replace $closePattern, ''

$srcSha = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
$extSha = ([BitConverter]::ToString(
        [Security.Cryptography.SHA256]::Create().ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($text))) -replace '-', '')

$srcBytes = ([System.IO.FileInfo]$SourcePath).Length
$extBytes = [Text.Encoding]::UTF8.GetByteCount($text)

$srcLines = ($sourceRaw -split "`n").Count
$extLines = ($text -split "`n").Count

$ok = ($srcSha -eq $extSha) -and ($srcBytes -eq $extBytes) -and ($srcLines -eq $extLines)

[PSCustomObject]@{
    Spec            = $SpecPath
    Source          = $SourcePath
    SourceSha256    = $srcSha
    ExtractedSha256 = $extSha
    SourceBytes     = $srcBytes
    ExtractedBytes  = $extBytes
    SourceLines     = $srcLines
    ExtractedLines  = $extLines
    Verbatim        = $ok
    SpecBytes       = ([System.IO.FileInfo]$SpecPath).Length
} | Format-List

if (-not $ok) { throw "Verbatim verification FAILED for $SpecPath" }
