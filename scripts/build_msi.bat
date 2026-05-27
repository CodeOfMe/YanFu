@echo off
REM Build MSI installer for Windows with bundled models
REM Usage: build_msi.bat [model_name]
REM
REM Prerequisites:
REM   pip install briefcase
REM   Python 3.10+ installed
REM
REM This script:
REM 1. Downloads the specified model (default: gemma3:1b)
REM 2. Bundles it in the MSI installer
REM 3. Creates a self-contained installer

setlocal enabledelayedexpansion

set MODEL_NAME=%1
if "%MODEL_NAME%"=="" set MODEL_NAME=gemma3:1b

echo === YanFu MSI Builder ===
echo Model: %MODEL_NAME%
echo.

REM Step 1: Download model
echo [1/4] Downloading model...
python scripts\bundle_models.py --model %MODEL_NAME% --output models
if %errorlevel% neq 0 (
    echo Error: Failed to download model
    exit /b 1
)

REM Step 2: Verify model
echo [2/4] Verifying model...
for %%f in (models\*.gguf) do set MODEL_PATH=%%f
if "%MODEL_PATH%"=="" (
    echo Error: No GGUF model found in models\
    exit /b 1
)
echo Model: %MODEL_PATH%

REM Step 3: Build with Briefcase
echo [3/4] Building MSI with Briefcase...
briefcase create windows msi
briefcase build windows msi

REM Step 4: Package
echo [4/4] Creating installer...
briefcase package windows msi

echo.
echo === Build Complete ===
echo MSI installer created in dist\
echo.
echo Installation instructions:
echo 1. Double-click the MSI file to install
echo 2. Launch YanFu from Start Menu or Desktop
echo 3. Models are pre-installed, no download needed
echo 4. Works completely offline after installation

endlocal
