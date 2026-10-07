@echo off
REM Start the Sanjeevani Clinic app (Windows).
cd /d "%~dp0"

if not exist .env (
    echo No .env found - copying .env.example to .env
    copy .env.example .env >nul
    echo Open .env and set DB_PASSWORD ^(and GROQ_API_KEY if you want AI^).
)

REM Train if the model is missing OR cannot be loaded (scikit-learn pickles
REM are not portable between scikit-learn versions).
python -c "import sys; sys.path.insert(0,'.'); from src.pipeline.predict_pipeline import model_available; ok,_ = model_available(); sys.exit(0 if ok else 1)" 2>nul
if errorlevel 1 (
    echo Training the screening model ^(missing or incompatible artifacts^)...
    python train_model.py
)

echo.
echo Starting on http://127.0.0.1:8000   ^(press Ctrl+C to stop^)
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
