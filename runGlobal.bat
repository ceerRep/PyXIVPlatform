@echo off
%~d0
cd %~dp0
python run.py config_Global

if NOT %ERRORLEVEL%==0 pause