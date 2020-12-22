@echo off
%~d0
cd %~dp0
powershell.exe -Command python run.py config_common config_Global config_user_Global

if NOT %ERRORLEVEL%==0 pause