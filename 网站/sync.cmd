@echo off
setlocal

set "SITE_DIR=%~dp0"
set "REPO_DIR=%SITE_DIR%.."

pushd "%REPO_DIR%" || exit /b 1

echo [1/3] Stage website files...
git add -- "%SITE_DIR%."
if errorlevel 1 goto :failed

echo [2/3] Commit website changes...
git diff --cached --quiet -- "%SITE_DIR%."
if %errorlevel%==0 (
  echo No website changes to sync.
  popd
  exit /b 0
)
git commit -m "chore: sync corrosion research website"
if errorlevel 1 goto :failed

echo [3/3] Push to GitHub main...
git push origin main
if errorlevel 1 goto :failed

echo Website sync completed.
popd
exit /b 0

:failed
echo Website sync failed. Review the Git output above.
popd
exit /b 1
