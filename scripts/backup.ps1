# Windows wrapper: runs backup.sh through Git Bash (ships with Git for Windows).
# Schedule nightly with Task Scheduler:
#   powershell -File C:\path\to\mediastack\scripts\backup.ps1 -BackupDir D:\Backups
param([string]$BackupDir = "")
$bash = "$env:ProgramFiles\Git\bin\bash.exe"
if (-not (Test-Path $bash)) { throw "Git Bash not found at $bash" }
$script = Join-Path $PSScriptRoot "backup.sh"
if ($BackupDir) { & $bash $script ($BackupDir -replace '\', '/') } else { & $bash $script }
exit $LASTEXITCODE
