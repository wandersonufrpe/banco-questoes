@echo off
rem Gera a pasta portatil do Banco de Questoes para Windows:
rem   empacotamento\saida\dist\BancoQuestoes\BancoQuestoes.exe
rem   empacotamento\saida\BancoQuestoes-<versao>-windows-x64.zip
rem
rem Requisitos so na maquina de build: Python 3.11+ (python.org), com o "py" launcher.
rem Uso: empacotamento\build_windows.bat     (opcional: set SEM_TESTES=1)
setlocal enableextensions
cd /d "%~dp0\.."
set RAIZ=%CD%
set SAIDA=%RAIZ%\empacotamento\saida

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv-build\Scripts\python.exe" (
  echo ^>^> Criando ambiente virtual
  %PY% -m venv .venv-build || goto :erro
)
call ".venv-build\Scripts\activate.bat" || goto :erro
python -m pip install --upgrade pip || goto :erro
python -m pip install -r requirements-dev.txt || goto :erro

if not defined SEM_TESTES (
  echo ^>^> Rodando os testes
  python -m pytest -q || goto :erro
)

echo ^>^> PyInstaller
if exist "%SAIDA%\dist" rmdir /s /q "%SAIDA%\dist"
if exist "%SAIDA%\build" rmdir /s /q "%SAIDA%\build"
pyinstaller --noconfirm --clean --distpath "%SAIDA%\dist" --workpath "%SAIDA%\build" empacotamento\bancoq.spec || goto :erro

for /f %%v in ('python -c "import bancoq; print(bancoq.__version__)"') do set VERSAO=%%v
echo ^>^> Compactando a pasta portatil
powershell -NoProfile -Command "Compress-Archive -Path '%SAIDA%\dist\BancoQuestoes' -DestinationPath '%SAIDA%\BancoQuestoes-%VERSAO%-windows-x64.zip' -Force" || goto :erro

echo.
echo Pronto: %SAIDA%\dist\BancoQuestoes\BancoQuestoes.exe
echo         %SAIDA%\BancoQuestoes-%VERSAO%-windows-x64.zip
exit /b 0

:erro
echo.
echo O build falhou. Veja as mensagens acima.
exit /b 1
