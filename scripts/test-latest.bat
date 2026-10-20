@echo off
chcp 65001 >nul
rem Скачивает установщик последней успешной сборки Release из GitHub Actions для ветки
rem и запускает его поверх установленной версии. Настройки и данные сохраняются.
rem   scripts\test-latest.bat                 — ветка облачной сессии
rem   scripts\test-latest.bat main            — другая ветка
rem Нужен GitHub CLI (winget install --id GitHub.cli) и вход: gh auth login.
setlocal
set "REPO=kuzak018-arch/ddddq"
set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=claude/quirky-heisenberg-i3ggds"

where gh >nul 2>nul || (echo Нет GitHub CLI: winget install --id GitHub.cli & exit /b 1)
gh auth status >nul 2>nul || (echo Сначала войди в GitHub: gh auth login & exit /b 1)

set "RUN="
for /f "usebackq delims=" %%i in (`gh run list -R %REPO% --workflow release.yml --branch "%BRANCH%" --status success --limit 1 --json databaseId -q ".[0].databaseId"`) do set "RUN=%%i"
if "%RUN%"=="" (
  echo Нет успешной сборки Release для ветки %BRANCH%.
  echo Запусти её: GitHub - Actions - Release - Run workflow - ветка %BRANCH%.
  exit /b 1
)
echo Сборка %RUN% для ветки %BRANCH%

set "OUT=%TEMP%\dota-drafter-test"
if exist "%OUT%" rmdir /s /q "%OUT%"
gh run download %RUN% -R %REPO% -D "%OUT%" || (echo Не удалось скачать артефакт сборки %RUN% & exit /b 1)

set "EXE="
for /r "%OUT%" %%f in (*-setup.exe) do set "EXE=%%f"
if "%EXE%"=="" (echo В артефакте нет установщика & exit /b 1)
echo Запускаю %EXE%
echo Закрой Dota Drafter, если он открыт: установщик заменит программу, данные останутся.
start "" /wait "%EXE%"
echo Готово.
endlocal
