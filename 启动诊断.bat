@echo off
cd /d "%~dp0"
HuanjingWallpaperGallery.exe
set APP_EXIT=%errorlevel%
if not "%APP_EXIT%"=="0" (
  echo.
  echo The application exited with code %APP_EXIT%.
  echo Check %%LOCALAPPDATA%%\HuanjingWallpaperGallery\crash.log
  pause
)
