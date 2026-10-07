"""Rebuild the ML artifacts used by the /predict (Covid screening) page.

The app reads ``artifacts/model.pkl`` and ``artifacts/preprocessor.pkl``. Those
files are git-ignored, so a fresh clone has none and the prediction page used to
silently fall back to a hand-written scoring rule while still displaying a
"Model confidence" percentage.

Run this once after cloning (it takes a few seconds):

    python train_model.py

It is also safe to run again at any time.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.components.data_ingestion import DataIngestion
from src.components.data_transformation import DataTransformation
from src.components.model_trainer import ModelTrainer


def main() -> int:
    print("=" * 70)
    print("Training the Covid screening model")
    print("=" * 70)

    print("\n[1/3] Data ingestion ...")
    train_path, test_path = DataIngestion().initiate_data_ingestion()
    print(f"      train: {train_path}")
    print(f"      test : {test_path}")

    print("\n[2/3] Data transformation ...")
    train_arr, test_arr, preprocessor_path = (
        DataTransformation().initiate_data_transformation(
            train_path, test_path
        )
    )
    print(f"      preprocessor saved: {preprocessor_path}")

    print("\n[3/3] Model training ...")
    best_name, best_score = ModelTrainer().initiate_model_trainer(
        train_arr, test_arr
    )

    print("\n" + "=" * 70)
    print(f"Best model : {best_name}")
    print(f"Accuracy   : {float(best_score):.4f}")
    print(
        "Artifacts  : "
        f"{BASE_DIR / 'artifacts' / 'model.pkl'} , "
        f"{BASE_DIR / 'artifacts' / 'preprocessor.pkl'}"
    )
    print("=" * 70)

    if float(best_score) < 0.7:
        print(
            "\nNOTE: accuracy is low. That is expected here - "
            "notebook/data/covid_toy.csv is a tiny 100-row practice "
            "dataset, not real clinical data. Do not treat this model's "
            "output as a medical test."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
