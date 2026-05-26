import os
import sys
import numpy as np
import pandas as pd
import xgboost as xgb
import time
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts"

# Define the exact feature contract the model expects
FEATURE_COLUMNS = ["total_transactions_30d", "total_amount_30d", "avg_amount_30d"]

def generate_synthetic_data(num_samples=1000):
    """Generates mock training data to simulate historical customer behavior."""
    np.random.seed(42)

    # Generate random features
    transactions = np.random.randint(1, 50, size=num_samples)
    avg_amounts = np.random.uniform(10.0, 500.0, size=num_samples)
    total_amounts = transactions * avg_amounts

    df = pd.DataFrame({
        "total_transactions_30d": transactions,
        "total_amount_30d": total_amounts,
        "avg_amount_30d": avg_amounts
    })

    # Create a synthetic target: let's pretend high volume + high average = higher risk of fraud (1)
    # This creates a recognizable pattern for the XGBoost model to learn
    risk_score = (df["total_transactions_30d"] / 50) + (df["avg_amount_30d"] / 500)
    probabilities = np.clip(risk_score / 2, 0, 1)
    df["target"] = np.random.binomial(1, probabilities)

    return df

def train_model():
    """Trains the XGBoost model and saves the artifact to disk."""
    version = f"v_{int(time.time())}"

    # Ensure artifact directory exists
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    logger.info("Generating synthetic training data...")
    df = generate_synthetic_data(num_samples=2000)

    X = df[FEATURE_COLUMNS]
    y = df["target"]

    # Split into train and validation sets
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    logger.info("Training XGBoost model...")
    # Initialize model with constraints to prevent overfitting
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        early_stopping_rounds=10, # Stops training if validation doesn't improve
        eval_metric="auc"         # Use Area Under the Curve for imbalanced/binary data
    )

    # Fit the model
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    # Evaluate performance
    val_predictions = model.predict_proba(X_val)[:, 1]
    auc_score = roc_auc_score(y_val, val_predictions)
    logger.info(f"Model trained successfully. Validation AUC: {auc_score:.4f}")

    # Save the model
    model_path = os.path.join(ARTIFACT_DIR, f"model_{version}.json")
    model.save_model(model_path)
    logger.info(f"Model saved to {model_path}")

    # 1. Update Continuous Training (CT) pointer
    latest_path = os.path.join(ARTIFACT_DIR, "latest_version.txt")
    with open(latest_path, "w") as f:
        f.write(version)

    # 2. Update Continuous Deployment (CD) pointer with interactive prompt
    active_path = os.path.join(ARTIFACT_DIR, "active_version.txt")
    if not os.path.exists(active_path):
        with open(active_path, "w") as f:
            f.write(version)
        logger.info(f"Model {version} registered as latest and initialized as active.")
    else:
        # Interactive Prompt Logic
        if sys.stdin.isatty():
            choice = input(f"\nNew model '{version}' trained! Promote to ACTIVE production model? [Y/n]: ").strip().lower()
            if choice in ['', 'y', 'yes']:
                with open(active_path, "w") as f:
                    f.write(version)
                logger.info(f"SUCCESS: Model {version} manually promoted to active.")
            else:
                logger.info(f"Model {version} kept as latest only. Active model remains unchanged.")
        else:
            # Automated fallback if running in a background CI/CD pipeline
            logger.info(f"Model {version} registered as latest. (Run --set-active-model to promote it).")

def score_customers(features_list):
    """Loads the model artifact and generates predictions for a list of customer features."""

    active_version = os.getenv("MODEL_VERSION")
    active_path = os.path.join(ARTIFACT_DIR, "active_version.txt")
    latest_path = os.path.join(ARTIFACT_DIR, "latest_version.txt")

    if not active_version:
        # 1. Look for the structured active pointer first
        if os.path.exists(active_path):
            with open(active_path, "r") as f:
                active_version = f.read().strip()
        # 2. Fall back to latest if active is missing
        elif os.path.exists(latest_path):
            with open(latest_path, "r") as f:
                active_version = f.read().strip()
        # 3. If nothing exists, train a new one
        else:
            logger.warning("No model registry found. Triggering offline training...")
            train_model()
            with open(active_path, "r") as f:
                active_version = f.read().strip()

    model_path = os.path.join(ARTIFACT_DIR, f"model_{active_version}.json")

    if not os.path.exists(model_path):
        logger.error(f"Requested model version {active_version} not found at {model_path}.")
        return []

    # Status tags for logging
    is_active = False
    is_latest = False

    if os.path.exists(active_path):
        with open(active_path, "r") as f:
            if active_version == f.read().strip():
                is_active = True

    if os.path.exists(latest_path):
        with open(latest_path, "r") as f:
            if active_version == f.read().strip():
                is_latest = True

    if is_active:
        status_tag = "(ACTIVE PROD)"
    elif is_latest:
        status_tag = "(LATEST OVERRIDE)"
    else:
        status_tag = "(CUSTOM/HISTORICAL OVERRIDE)"

    logger.info(f"Loading model version '{active_version}' {status_tag} for scoring...")

    model = xgb.XGBClassifier()
    model.load_model(model_path)

    # Convert incoming list of dictionaries to a Pandas DataFrame
    df_scoring = pd.DataFrame(features_list)

    # Ensure we only pass the exact features the model was trained on (in the correct order)
    X_score = df_scoring[FEATURE_COLUMNS]

    # Predict probabilities (predict_proba returns [prob_class_0, prob_class_1])
    # We want the probability of class 1
    scores = model.predict_proba(X_score)[:, 1]

    # Combine the IDs back with the scores
    results = []
    for i, row in df_scoring.iterrows():
        results.append({
            "customer_id": row["customer_id"],
            "score": round(float(scores[i]), 4)
        })

    return results

# --- TEST ---
if __name__ == "__main__":
    # 1. Train the model (this will create the JSON file in /artifacts)
    train_model()

    # 2. Simulate data coming from the 'feature-updates' topic
    mock_feature_updates = [
        {
            "customer_id": "C-001-NEW",  # Very little history
            "total_transactions_30d": 1,
            "total_amount_30d": 15.0,
            "avg_amount_30d": 15.0
        },
        {
            "customer_id": "C-002-AVERAGE",  # Standard user
            "total_transactions_30d": 12,
            "total_amount_30d": 450.0,
            "avg_amount_30d": 37.5
        },
        {
            "customer_id": "C-003-HIGH-RISK",  # Extreme volume and amount
            "total_transactions_30d": 85,
            "total_amount_30d": 45000.0,
            "avg_amount_30d": 529.41
        },
        {
            "customer_id": "C-004-MICRO-TXNS",  # High volume, tiny amounts (bot behavior?)
            "total_transactions_30d": 150,
            "total_amount_30d": 150.0,
            "avg_amount_30d": 1.0
        },
        {
            "customer_id": "C-005-WHALE",  # Few transactions, massive amounts
            "total_transactions_30d": 3,
            "total_amount_30d": 18000.0,
            "avg_amount_30d": 6000.0
        }
    ]

    # 3. Generate scores
    print("\n--- Generating Scores for 5 Example Customers ---")
    final_scores = score_customers(mock_feature_updates)

    # Print the results in a clean, readable format
    print(f"{'Customer ID':<20} | {'Fraud Risk Score'}")
    print("-" * 40)
    for res in final_scores:
        print(f"{res['customer_id']:<20} | {res['score']:.4f}")
