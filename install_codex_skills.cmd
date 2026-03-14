@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_codex_skills.ps1"
endlocal
