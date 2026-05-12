@echo off
%~d0
cd %~dp0
uv run python run.py config_common config_CN config_user_CN

if NOT %ERRORLEVEL%==0 pause
