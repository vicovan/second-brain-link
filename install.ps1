# Second Brain Link — installer for Windows (macOS / Linux: install.sh).
#
# Installs the brain builder skill and the agents (Jobs, Fundraising, Travel) for the AI tools
# on this computer: Claude Code -> %USERPROFILE%\.claude\skills\<name>,
# Codex -> %USERPROFILE%\.agents\skills\<name>. No git and no Python needed to install.
# Every file is checked against dist/manifest.json.
#
#   irm https://secondbrainlink.com/install.ps1 | iex
#   & ([scriptblock]::Create((irm https://secondbrainlink.com/install.ps1))) -Claude -NoAgents
#
# Safe by design: only writes .claude\skills\<our names> and .agents\skills\<our names>, never
# touches a link there (a developer install), and swaps a folder in only after it unpacked cleanly.
param(
  [switch]$Claude,
  [switch]$Codex,
  [switch]$NoAgents,
  [string]$FromDir = '',
  [string]$BaseUrl = 'https://github.com/vicovan/second-brain-link/raw/main/dist/'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host 'Second Brain Link installer'
$HomeDir = [Environment]::GetFolderPath('UserProfile')

if (-not $Claude -and -not $Codex) {
  if ((Get-Command claude -ErrorAction SilentlyContinue) -or (Test-Path "$HomeDir\.claude")) { $Claude = $true }
  if ((Get-Command codex -ErrorAction SilentlyContinue) -or (Test-Path "$HomeDir\.codex")) { $Codex = $true }
  if (-not $Claude -and -not $Codex) { $Claude = $true }
}

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ('sbl-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Tmp | Out-Null

function Get-Artifact([string]$rel, [string]$dest) {
  if ($FromDir) { Copy-Item (Join-Path $FromDir $rel) $dest }
  else { Invoke-WebRequest -UseBasicParsing -Uri ($BaseUrl + $rel) -OutFile $dest }
}

try {
  Get-Artifact 'manifest.json' "$Tmp\manifest.json"
  $manifest = Get-Content "$Tmp\manifest.json" -Raw | ConvertFrom-Json
  $installed = 0
  foreach ($a in $manifest.artifacts) {
    if ($a.provider -eq 'claude' -and -not $Claude) { continue }
    if ($a.provider -eq 'codex' -and -not $Codex) { continue }
    if ($a.kind -eq 'agent' -and $NoAgents) { continue }
    $tool = if ($a.provider -eq 'claude') { 'Claude Code' } else { 'Codex' }
    $label = "$($a.name) $($a.version) for $tool"
    $dest = Join-Path $HomeDir ($a.installs_to -replace '/', '\')
    $item = Get-Item $dest -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType) { Write-Host "  ! ${label}: $dest is a developer link - left as is"; continue }
    $arc = Join-Path $Tmp "$($a.provider)-$($a.name).zip"
    try { Get-Artifact $a.file $arc } catch { Write-Host "  ! ${label}: download failed"; continue }
    if ((Get-FileHash $arc -Algorithm SHA256).Hash.ToLower() -ne $a.sha256) { Write-Host "  ! ${label}: checksum mismatch - skipped"; continue }
    $ex = Join-Path $Tmp "ex-$($a.provider)-$($a.name)"
    Expand-Archive -Path $arc -DestinationPath $ex -Force
    $new = Join-Path $ex $a.name
    if (-not (Test-Path $new)) { Write-Host "  ! ${label}: unexpected archive layout - skipped"; continue }
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    if (Test-Path $dest) {
      $old = "$dest.old"
      if (Test-Path $old) { Remove-Item $old -Recurse -Force }
      Move-Item $dest $old
      try { Move-Item $new $dest; Remove-Item $old -Recurse -Force }
      catch { Move-Item $old $dest; Write-Host "  ! ${label}: could not replace"; continue }
    } else { Move-Item $new $dest }
    @{ name = $a.name; provider = $a.provider; version = $a.version; rev = $a.rev; installedBy = 'install.ps1' } |
      ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $dest '.sbl-install.json')
    Write-Host "  + $label -> ~\$($a.installs_to -replace '/', '\')"
    $installed++
  }
  if ($installed -eq 0) { throw 'Nothing was installed.' }

  Write-Host ''
  Write-Host 'Next steps'
  if (-not ((Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue))) {
    Write-Host '  * Python 3 is needed to build a brain from the terminal:  winget install Python.Python.3.12'
    Write-Host '    The desktop app (secondbrainlink.com/download) has Python built in.'
  }
  if ($Claude -and -not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host '  * Install Claude Code:  irm https://claude.ai/install.ps1 | iex    then: claude auth login'
  }
  if ($Codex -and -not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Host '  * Install Codex:  irm https://chatgpt.com/codex/install.ps1 | iex    then: codex login'
  }
  Write-Host '  * Open Claude Code (or Codex) and say: "Build my second brain from my data exports."'
  Write-Host '  * Or use the desktop app, which does all of this for you: https://secondbrainlink.com/download'
}
finally {
  Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}
