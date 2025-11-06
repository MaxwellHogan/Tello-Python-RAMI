@echo off
REM ========================================
REM Run Tello Python dev container on Windows
REM ========================================

REM Name of the container
set CONTAINER_NAME=tello-dev-container

REM Name of the image
set IMAGE_NAME=tello-dev

echo Starting container "%CONTAINER_NAME%" from image "%IMAGE_NAME%"

docker run -it --rm ^
    --name %CONTAINER_NAME% ^
    --network host ^
    -e DISPLAY=host.docker.internal:0 ^
    -v "C:\dji_tello\Tello-Python":/app ^
    %IMAGE_NAME%
