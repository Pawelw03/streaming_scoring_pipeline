# Streaming Feature Builder & Scoring Service

This repository contains a simulated event-driven machine learning pipeline. It processes a stream of customer transactions, calculates 30-day sliding window features with state management, and serves predictions using a pre-trained XGBoost model.

## Project Structure

* `src/feature_builder.py`: Manages customer state, handles out-of-order events, enforces idempotency, and calculates sliding window features.
* `src/train_and_score.py`: Handles synthetic data generation, XGBoost model training (with AUC evaluation), and inference.
* `src/app.py`: The main entrypoint that wires the simulated Kafka stream (JSONL) to the feature builder and scoring service.
* `docs/`: Contains architectural design and reflection documents.
* `data/`: Contains the simulated `events.jsonl` Kafka stream.
* `artifacts/`: Stores the trained model binaries (`model_v_*.json`) and the registry pointers (`active_version.txt`, `latest_version.txt`).

---

## How to Run

### Method 1: Using Docker (Recommended)
This is the standard, reproducible way to run the pipeline end-to-end.

1. **Build the image:**
   ```bash
   docker build -t streaming-score .
   ```

2. **Run the container:**
   ```bash
   docker run --rm streaming-score
   ```
*???(Note: To persist newly trained models or pointer changes back to your local machine, map the artifacts volume: `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score`)*

### Method 2: Local Python Environment
If you want to run the code locally for development or testing.

1. **Set up the virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the pipeline:**
   ```bash
   python -m src.app --events data/events.jsonl
   ```

---

## CLI Flags

The pipeline includes built-in operational tooling to manage the machine learning lifecycle via command-line flags. It separates Continuous Training (CT) from Continuous Deployment (CD) using `latest_version.txt` and `active_version.txt`.

* **Force Model Retraining (`--retrain`)**
  Manually overrides the pipeline to trigger an offline training job before scoring. It generates new synthetic data, trains a new XGBoost version, and updates the `latest_version.txt` registry. Locally, it interactively prompts you to promote the new model to ACTIVE.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --retrain`
  * **Local:** `python -m src.app --retrain`

* **Set Active Model / Promote (`--set-active-model`)**
  Administrative command to permanently update the `active_version.txt` pointer to a specific model version. Exits without processing the stream. Supports the `latest` alias.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --set-active-model latest`
  * **Local:** `python -m src.app --set-active-model="v_1716560000"`

* **Model Rollback / Hot-Swapping (`--model-version`)**
  Temporarily bypasses the `active_version.txt` registry and forces the scoring service to load a specific historical model version for inference. Supports the `latest` alias.
  * **Docker:** `docker run --rm streaming-score --model-version latest`
  * **Local:** `python -m src.app --model-version="v_1716560000"`

* **Custom Event Stream (`--events`)**
  Points the pipeline to a different JSONL stream file. This can also be configured by setting the `EVENTS_PATH` environment variable.
  * **Local:** `python -m src.app --events path/to/custom_events.jsonl`

---

## Documentation

Refer to the `docs/` directory for system design decisions:

* **`docs/architecture.md`**: Details on Kafka topics, DynamoDB state management, NoSQL access patterns, and Model CI/CD.
* **`docs/reflection.md`**: Discussion on edge cases, training-serving skew, and future ecosystem improvements.
