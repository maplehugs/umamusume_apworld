# Set up (first run) and start the UmaPS Global server + admin panel. Windows.
#   Right-click -> Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File start-global.ps1
#   Options: --no-admin (don't open the admin panel), --help (all options)
Set-Location $PSScriptRoot
foreach ($c in @(@('py', '-3'), @('python'), @('python3'))) {
    $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @pre -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $exe @pre server/launcher.py --region global @args
        if ($LASTEXITCODE -ne 0) { Read-Host 'Press Enter to close' }
        exit $LASTEXITCODE
    }
}
Write-Host 'Python 3.11 or newer is required: https://www.python.org/downloads/'
Write-Host '(tick "Add python.exe to PATH" in the installer, then run this again)'
Read-Host 'Press Enter to close'
exit 1
