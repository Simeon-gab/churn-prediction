"""
train_model.py
--------------
Trains the Random Forest churn model and saves it to data/models/.

Run this manually when you want to retrain:
    cd churn_prediction
    python -m src.models.train_model

It will:
    1. Load the three raw CSVs
    2. Build the feature matrix
    3. Stratified 80/20 train/test split
    4. Train RandomForestClassifier (400 trees, balanced class weights)
    5. Print classification report + ROC-AUC on the test set
    6. Save the trained model to data/models/churn_model.pkl

The feature columns used at training time are also saved as a sidecar
JSON file, so predict_model.py can reindex new data to the same schema.
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split

from src.data.load_data import load_subscriptions, load_usage, load_tickets
from src.features.build_features import build_features


MODEL_PATH = Path("data/models/churn_model.pkl")
FEATURES_PATH = Path("data/models/feature_columns.json")


def train() -> RandomForestClassifier:
    """Train the model end-to-end and persist artifacts."""

    # 1. Load raw data
    print("Loading raw data...")
    subs = load_subscriptions()
    usage = load_usage()
    tickets = load_tickets()

    # 2. Build features
    print("Building features...")
    X_encoded, meta = build_features(subs, usage, tickets)
    y = meta["churn_flag"]

    # 3. Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_encoded,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    print(f"Train shape: {X_train.shape}  |  Test shape: {X_test.shape}")

    # 4. Train
    print("Training RandomForest...")
    model = RandomForestClassifier(
        n_estimators=400,
        max_depth=None,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # 5. Evaluate
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)

    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))
    print(f"\nROC-AUC Score: {roc_auc_score(y_test, y_prob):.4f}")
    print(f"Max probability: {y_prob.max():.4f}")
    print(f"Mean probability: {y_prob.mean():.4f}")

    # 6. Save model and the feature schema
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    with open(FEATURES_PATH, "w") as f:
        json.dump(list(X_encoded.columns), f, indent=2)

    print(f"\nModel saved to {MODEL_PATH}")
    print(f"Feature schema saved to {FEATURES_PATH}")

    return model


if __name__ == "__main__":
    train()
