# NEXUS phone bridge (desktop). Runs Claude Code Remote Control in server mode from the NEXUS folder,
# so I can start fresh, short sessions from the Claude phone app (Code tab, tap the desktop).
# Each phone job gets its own session, so no session grows huge.
#
# First time (from PowerShell, run as yourself, not as admin):
#   powershell -NoProfile -ExecutionPolicy Bypass -File phone-bridge.ps1 -Setup
#     Checks the claude command, stops the tower sleeping on mains power, adds the logon task, starts it.
# Run by hand:   powershell -NoProfile -ExecutionPolicy Bypass -File phone-bridge.ps1
# Undo:          powershell -NoProfile -ExecutionPolicy Bypass -File phone-bridge.ps1 -Remove
# Log:           %LOCALAPPDATA%\NEXUS\phone-bridge\bridge.log (outside OneDrive, per machine)

param([switch]$Setup, [switch]$Remove)

$TaskName = 'NEXUS Phone Bridge'
$Nexus = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$LogDir = Join-Path $env:LOCALAPPDATA 'NEXUS\phone-bridge'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'bridge.log'
function Say($m) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m"; Write-Host $line; Add-Content $Log $line }

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Say "Removed the '$TaskName' task. Sleep setting left as it is (undo: powercfg /change standby-timeout-ac 30)."
    exit 0
}

$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Say "STOP: no 'claude' command on this machine. Server mode needs the Claude Code CLI, not just the VS Code extension."
    Say "Install it (free, needs the owner's yes first), open a new PowerShell, then run this again."
    exit 1
}

if ($Setup) {
    powercfg /change standby-timeout-ac 0 | Out-Null
    Say "Sleep on mains power: never."
    $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    # Windows 11 hands consoles to Windows Terminal, which ignores -WindowStyle Hidden. conhost --headless gives no window at all.
    $action = New-ScheduledTaskAction -Execute 'conhost.exe' -Argument "--headless powershell.exe $arg"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = 'PT2M'   # give OneDrive time to have the Desktop ready (same lesson as the Agentic OS)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Say "Logon task '$TaskName' added (starts 2 min after logon)."
}

# Don't start a second server if one is already running from this folder.
$running = Get-CimInstance Win32_Process -Filter "Name like 'claude%' or Name = 'node.exe'" |
    Where-Object { $_.CommandLine -match 'remote-control' }
if ($running) { Say "Bridge already running (pid $($running[0].ProcessId)). Nothing to do."; exit 0 }

Set-Location $Nexus
Say "Starting Remote Control server in $Nexus"
& $claude.Source remote-control --spawn same-dir --permission-mode auto 2>&1 | Tee-Object -FilePath $Log -Append
Say "Server stopped (exit $LASTEXITCODE)."
