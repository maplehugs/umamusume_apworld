@echo off
rem Double-click to start the server. Runs start-global.ps1 without changing the
rem system's PowerShell policy (Windows blocks .ps1 files by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-global.ps1" %*
