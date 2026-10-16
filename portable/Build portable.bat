@echo off
rem Developer tool: builds dist\Generator-portable.zip for users without Python.
rem Needs internet and a Python 3.12 on this computer (set GENERATOR_BUILD_PYTHON if it is not "python").
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_portable.ps1" %*
pause
