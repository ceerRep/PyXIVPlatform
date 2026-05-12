@echo off
%~d0
cd %~dp0
uv run python run.py config_common config_Global config_user_Global

if NOT %ERRORLEVEL%==0 pause
