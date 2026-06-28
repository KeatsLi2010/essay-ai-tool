param(
  [string]$HostName = "0.0.0.0",
  [int]$AdminPort = 8765,
  [int]$GuestPort = 8766,
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Stop-PortListener {
  param([int]$Port)
  $listener = netstat -ano | Select-String ":$Port" | Select-String "LISTENING" | Select-Object -First 1
  if ($listener -and $listener.ToString() -match "\s+(\d+)$") {
    Stop-Process -Id ([int]$Matches[1]) -Force -ErrorAction SilentlyContinue
  }
}

Stop-PortListener -Port $AdminPort
Stop-PortListener -Port $GuestPort

$adminOut = Join-Path $LogDir "admin.out.log"
$adminErr = Join-Path $LogDir "admin.err.log"
$guestOut = Join-Path $LogDir "guest.out.log"
$guestErr = Join-Path $LogDir "guest.err.log"

Start-Process `
  -FilePath $Python `
  -ArgumentList @("-m", "web_app", "--host", $HostName, "--port", [string]$AdminPort) `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $adminOut `
  -RedirectStandardError $adminErr

Start-Process `
  -FilePath $Python `
  -ArgumentList @("-m", "web_app", "--guest", "--host", $HostName, "--port", [string]$GuestPort) `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $guestOut `
  -RedirectStandardError $guestErr

Start-Sleep -Seconds 1

foreach ($port in @($AdminPort, $GuestPort)) {
  try {
    $status = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port" -TimeoutSec 3).StatusCode
    Write-Host "$port $status"
  } catch {
    Write-Host "$port $($_.Exception.Message)"
  }
}

