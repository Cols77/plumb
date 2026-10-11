@echo off
rem plumb in the plugin's own environment, for cmd.exe (SP7 4.2): the same launcher as
rem bin/plumb, run by the sh that comes with Git for Windows.
sh "%~dp0plumb" %*
