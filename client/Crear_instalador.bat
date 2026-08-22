@echo off
REM Genera dist\eva.exe y dist\setup.exe. Doble clic y esperar.
REM
REM Se deja como .bat (y no como parte de la aplicacion) porque construir el
REM ejecutable es tarea de quien publica la version, no del piloto que vuela.

setlocal
cd /d "%~dp0"

echo ============================================
echo   EvA - creacion del instalador
echo ============================================
echo.

REM Buscar Python. El lanzador "py" es el que instala Python en Windows.
where py >nul 2>&1
if %errorlevel%==0 (
    set PY=py
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set PY=python
    ) else (
        echo No se ha encontrado Python en este equipo.
        echo Instalalo desde https://www.python.org/downloads/ y vuelve a
        echo ejecutar este fichero.
        echo.
        pause
        exit /b 1
    )
)

echo Usando: %PY%
%PY% --version
echo.

echo [1/3] Instalando dependencias del proyecto...
%PY% -m pip install -e . --quiet
if errorlevel 1 (
    echo.
    echo Fallo instalando las dependencias del proyecto.
    pause
    exit /b 1
)

echo [2/3] Instalando herramientas de empaquetado...
%PY% -m pip install pyinstaller pillow --quiet
if errorlevel 1 (
    echo.
    echo Fallo instalando PyInstaller.
    pause
    exit /b 1
)

echo [3/3] Empaquetando eva.exe y setup.exe (tarda un par de minutos)...
echo.
%PY% tools\build_exe.py
if errorlevel 1 (
    echo.
    echo El empaquetado ha fallado. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Listo. En la carpeta dist tienes:
echo     eva.exe    la aplicacion
echo     setup.exe  el instalador para los pilotos
echo ============================================
echo.

if exist "%~dp0dist" start "" "%~dp0dist"

pause
