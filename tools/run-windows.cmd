@echo off
setlocal
if not exist "%~1\images\main.bin" (
    echo Missing module images in "%~1\images".
    exit /b 2
)
if not exist "%~1\romfs\" (
    echo Missing RomFS directory "%~1\romfs".
    exit /b 2
)
if not exist "%~2" (
    echo Missing executable "%~2". Run tools\build-windows.py first.
    exit /b 2
)
set "TOTK_HEADLESS="
if /i "%~3"=="null" (
    set "TOTK_HEADLESS=1"
    set "TOTK_AUDIO=null"
)
set "TOTK_NVN_INT=0=53"
set "TOTK_LIFT_ALL=1"
set "TOTK_NO_OVERLAY=1"
set "TOTK_ROMFS=%~f1\romfs"
set "TOTK_USERDATA=%~dp2manual-userdata"
if not exist "%TOTK_USERDATA%\" mkdir "%TOTK_USERDATA%"
pushd "%~dp2" || exit /b 2
echo Log: "%~dp2run.log"
"%~f2" "%~f1\images" >"run.log" 2>&1
set "SP2_STATUS=%ERRORLEVEL%"
popd
echo Exit code: %SP2_STATUS%
exit /b %SP2_STATUS%
