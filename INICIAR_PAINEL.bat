@echo off
cd /d "%~dp0"
title Minha Carteira
python src\dashboard_server.py
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar o painel.
  echo Confirme se o Python esta instalado e tente novamente.
  pause
)
