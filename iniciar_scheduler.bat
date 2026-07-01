@echo off
setlocal EnableDelayedExpansion
title Scheduler Universitario

cd /d "%~dp0"

echo.
echo  ============================================================
echo    Scheduler Universitario  ^|  Planificacion de Cursos
echo  ============================================================
echo.

:: ── 1. Verificar Python ──────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo  Por favor descargue Python 3.10 o superior desde:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: durante la instalacion marque la opcion
    echo  "Add Python to PATH" antes de instalar.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python !PY_VER! encontrado.

:: ── 2. Configurar clave de encriptacion (.env) ───────────────────────────────
if exist ".env" goto :env_listo

echo.
echo  ------------------------------------------------------------
echo   Clave de encriptacion de RUT
echo  ------------------------------------------------------------
echo  Para mostrar los RUT de los profesores en la grilla se
echo  necesita la clave de encriptacion del proyecto (EncryptionKey).
echo.
echo  Pegue la clave y presione Enter.
echo  Si la deja en blanco, la aplicacion funcionara igual pero
echo  mostrara los RUT cifrados. Puede editar .env manualmente luego.
echo.
set "ENC_KEY="
set /p "ENC_KEY=  Clave: "
if defined ENC_KEY (
    >.env echo EncryptionKey="!ENC_KEY!"
    echo  Clave guardada en .env
) else (
    >.env echo EncryptionKey=""
    echo  Continuando sin clave: los RUT se mostraran cifrados.
)

:env_listo

:: ── 3. Crear entorno virtual si no existe ────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo  Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo  Entorno virtual creado.
)

call .venv\Scripts\activate.bat

:: ── 4. Instalar dependencias (solo la primera vez) ───────────────────────────
if not exist ".venv\.deps_ok" (
    echo.
    echo  Instalando dependencias...
    echo  ^(Esto puede tomar varios minutos la primera vez^)
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [ERROR] Fallo la instalacion de dependencias.
        echo  Verifique su conexion a internet e intente nuevamente.
        echo.
        pause
        exit /b 1
    )
    type nul > .venv\.deps_ok
    echo.
    echo  Dependencias instaladas correctamente.
)

:: ── 5. Iniciar aplicacion ────────────────────────────────────────────────────
echo.
echo  Iniciando la aplicacion...
echo  Se abrira automaticamente en su navegador.
echo.
echo  Si no abre, ingrese esta URL en su navegador:
echo    http://localhost:8501
echo.
echo  Para cerrar la aplicacion presione Ctrl+C en esta ventana
echo  o simplemente cierre esta ventana.
echo  ------------------------------------------------------------
echo.

python -m streamlit run app.py --browser.gatherUsageStats false

:: Llegado aqui, Streamlit fue cerrado
echo.
echo  La aplicacion se cerro.
pause
