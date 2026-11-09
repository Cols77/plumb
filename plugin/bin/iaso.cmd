@echo off
rem iaso in the plugin's own environment, for cmd.exe (SP7 4.2): the same launcher as
rem bin/iaso, run by the sh that comes with Git for Windows (SR-123 EX-3). cmd.exe's PATH
rem seldom holds sh (Git's installer adds only Git\cmd), so its sh.exe is found from git.exe
rem (Git\cmd\git.exe, Git\bin\git.exe or Git\mingw64\bin\git.exe: Git\bin\sh.exe is beside or
rem above it), then in the usual install folders, and only then as plain sh on the PATH.
setlocal
set "IASO_SH="
for /f "delims=" %%G in ('where git 2^>nul') do (
  if not defined IASO_SH if exist "%%~dpG..\bin\sh.exe" set "IASO_SH=%%~dpG..\bin\sh.exe"
  if not defined IASO_SH if exist "%%~dpG..\..\bin\sh.exe" set "IASO_SH=%%~dpG..\..\bin\sh.exe"
)
if not defined IASO_SH if exist "%ProgramFiles%\Git\bin\sh.exe" set "IASO_SH=%ProgramFiles%\Git\bin\sh.exe"
if not defined IASO_SH if exist "%LocalAppData%\Programs\Git\bin\sh.exe" set "IASO_SH=%LocalAppData%\Programs\Git\bin\sh.exe"
if not defined IASO_SH set "IASO_SH=sh"
"%IASO_SH%" "%~dp0iaso" %*
exit /b %ERRORLEVEL%
