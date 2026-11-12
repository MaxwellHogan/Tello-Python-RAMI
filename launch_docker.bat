
@echo off
REM ========================================
REM Run Tello Python dev container on Windows
REM ========================================

set "CONTAINER_NAME=tello-container"
set "IMAGE_NAME=tello-dev"
set "WORKING_DIRECTORY=C:\Tello-Python-RAMI"

echo Starting container "%CONTAINER_NAME%" from image "%IMAGE_NAME%"
echo Mounting "%WORKING_DIRECTORY%" to /workspace

docker run -it --rm ^
    --name %CONTAINER_NAME% ^
    --network host ^
    -e DISPLAY=host.docker.internal:0 ^
    --mount "type=bind,source=%WORKING_DIRECTORY%,target=/workspace" ^
    -w /workspace ^
    %IMAGE_NAME%
