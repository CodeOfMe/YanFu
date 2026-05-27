@echo off
REM YanFu - Build and upload to PyPI
setlocal enabledelayedexpansion

cd /d "%~dp0"

set PYTHON=%PYTHON%
if "!PYTHON!"=="" set PYTHON=python

echo === YanFu PyPI Upload ===

echo [1/5] Bumping patch version...
"%PYTHON%" -c "import re; p='src/yanfu/__init__.py'; t=open(p,encoding='utf-8').read(); m=re.search(r'(__version__\s*=\s*\"(\d+\.\d+\.)(\d+)\")', t); exec(\"if not m: print('ERROR: cannot parse version'); import sys; sys.exit(1)\nold_v = m.group(2) + m.group(3)\nnew_v = m.group(2) + str(int(m.group(3)) + 1)\nopen(p,'w',encoding='utf-8').write(t.replace(m.group(1), '__version__ = \\\"' + new_v + '\\\"'))\nprint(f'  {old_v} -^> {new_v}')\")"

echo [2/5] Cleaning old builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.egg-info del /q *.egg-info
if exist src\*.egg-info del /q src\*.egg-info

echo [3/5] Installing build tools...
"%PYTHON%" -m pip install --upgrade build twine -q

echo [4/5] Building package...
"%PYTHON%" -m build
"%PYTHON%" -m twine check dist\*

echo [5/5] Uploading to PyPI...
"%PYTHON%" -m twine upload dist\*

echo === Done! ===
endlocal
