#!/usr/bin/env bash
# Start the Sanjeevani Clinic app (Linux / macOS / Git Bash).
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found - copying .env.example to .env"
  cp .env.example .env
  echo ">> Open .env and set DB_PASSWORD (and GROQ_API_KEY if you want AI)."
fi

# Train if the model is missing OR cannot be loaded (scikit-learn pickles are
# not portable between scikit-learn versions, so a shipped model.pkl can be
# unusable on your machine until it is retrained).
if ! python -c "import sys; sys.path.insert(0,'.'); from src.pipeline.predict_pipeline import model_available; ok,_ = model_available(); sys.exit(0 if ok else 1)" 2>/dev/null; then
  echo "Training the screening model (missing or incompatible artifacts)..."
  python train_model.py
fi

echo
echo "Starting on http://127.0.0.1:8000   (press Ctrl+C to stop)"
echo
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
