@echo off
REM 检测 Inno Setup 6 ISCC.exe 路径，结果写入 iscc_detect_result.txt
set "RESULT="
powershell -Command "$p=$null; foreach ($d in @(($env:LOCALAPPDATA+'\Programs\Inno Setup 6'),([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')+'\Inno Setup 6'),($env:ProgramFiles+'\Inno Setup 6'))) { if (Test-Path (Join-Path $d 'ISCC.exe')) { $p=Join-Path $d 'ISCC.exe'; break } }; Write-Output $p" > "%~dp0iscc_detect_result.txt"
