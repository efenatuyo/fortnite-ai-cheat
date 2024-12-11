@echo off
SETLOCAL

echo Updating pip...
python -m pip install --upgrade pip

echo Installing required Python packages...
python -m pip install requests pygame ultralytics rich pywin32 bettercam

echo Checking for CUDA installation...
nvcc --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo CUDA not found! Please install CUDA from (make sure it is cu11) https://developer.nvidia.com/cuda-downloads.
    exit /b 1
)

echo Installing PyTorch with CUDA support...
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo Installation complete. You can now run your start.bat.
PAUSE
