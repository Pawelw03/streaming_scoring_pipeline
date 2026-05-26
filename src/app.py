import os
import json
import argparse
import logging
import sys
from src.feature_builder import FeatureBuilder
from src.train_and_score import score_customers, train_model

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="Streaming Feature Builder and ML Scorer")
    parser.add_argument(
        "--events",
        type=str,
        default=os.getenv("EVENTS_PATH", "data/events.jsonl"),
        help="Path to the JSONL file containing the event stream"
    )
    parser.add_argument(
        "--retrain",
        action="store_true",
        help="Force train a new model version before processing"
    )
    parser.add_argument(
        "--model-version",
        type=str,
        help="Specific model version to use for scoring (supports 'latest' alias)"
    )
    parser.add_argument(
        "--set-active-model",
        type=str,
        help="Command to update the active_version.txt pointer and exit (supports 'latest' alias)."
    )
    return parser.parse_args()

def resolve_version_alias(version_input):
    """Dynamically resolves human-readable aliases like 'latest' to actual version tags."""
    if version_input and version_input.lower() == "latest":
        latest_path = os.path.join("artifacts", "latest_version.txt")
        if os.path.exists(latest_path):
            with open(latest_path, "r") as f:
                resolved_version = f.read().strip()
                logger.info(f"Alias 'latest' resolved to actual version: '{resolved_version}'")
                return resolved_version
        else:
            logger.error("Cannot resolve 'latest'. File 'artifacts/latest_version.txt' not found.")
            sys.exit(1)
    return version_input

def main():
    args = parse_args()

    # --- Administrative Command Logic ---
    if args.set_active_model:
        target_version = resolve_version_alias(args.set_active_model)
        model_path = os.path.join("artifacts", f"model_{target_version}.json")
        active_path = os.path.join("artifacts", "active_version.txt")

        # Validate the model actually exists before updating the pointer
        if not os.path.exists(model_path):
            logger.error(f"Cannot set active model! File {model_path} does not exist.")
            sys.exit(1)

        # Update the pointer
        with open(active_path, "w") as f:
            f.write(target_version)

        logger.info(f"SUCCESS: 'active_version.txt' updated to point to '{target_version}'")
        sys.exit(0)  # Exit cleanly without running the streaming pipeline

    events_file = args.events

    # Temporary Override (Does not change active_version.txt)
    if args.model_version:
        target_version = resolve_version_alias(args.model_version)
        os.environ["MODEL_VERSION"] = target_version
        logger.info(f"Temporary override flag detected. Using model version: {target_version}")

    # Force Retrain Logic
    if args.retrain:
        logger.info("Manual retrain flag detected. Forcing model offline training...")
        train_model()

    if not os.path.exists(events_file):
        logger.error(f"Event file {events_file} not found. Please provide a valid path.")
        sys.exit(1)

    logger.info(f"Starting pipeline using stream from: {events_file}")

    # 1. Initialize Feature Builder
    builder = FeatureBuilder()
    active_customers = set()

    # 2. Process the stream
    logger.info("Processing event stream...")
    with open(events_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            event = json.loads(line)
            builder.process_event(event)
            active_customers.add(event["customer_id"])

    # 3. Extract the final features
    logger.info("Extracting current feature state...")
    feature_updates = []
    for customer_id in active_customers:
        features = builder.get_features(customer_id)
        if features:
            feature_updates.append(features)

    # 4. Generate Scores
    if not feature_updates:
        logger.warning("No features generated. Exiting.")
        sys.exit(0)

    logger.info("Generating predictions...")
    scores = score_customers(feature_updates)

    # 5. Output the final scores
    print("\n" + "="*50)
    print(f"{'Customer ID':<20} | {'Fraud Risk Score'}")
    print("-" * 50)
    if scores:
        for res in scores:
            print(f"{res['customer_id']:<20} | {res['score']:.4f}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
