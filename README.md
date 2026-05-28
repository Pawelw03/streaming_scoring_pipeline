# Streaming Feature Builder & Scoring Service

This repository contains a simulated event-driven machine learning pipeline. It processes a stream of customer transactions, calculates 30-day sliding window features with state management, and serves predictions using a pre-trained XGBoost model.

## Project Structure

* `src/feature_builder.py`: Manages customer state, handles out-of-order events, enforces idempotency, and calculates sliding window features.
* `src/train_and_score.py`: Handles synthetic data generation, XGBoost model training (with AUC evaluation), and inference.
* `src/app.py`: The main entrypoint that wires the simulated Kafka stream (JSONL) to the feature builder and scoring service.
* `docs/`: Contains architectural design and reflection documents.
* `data/`: Contains the simulated `events.jsonl` Kafka stream.
* `artifacts/`: Stores persistent customer state (`state.json`), trained model binaries (`model_v_*.json`), and the registry pointers (`active_version.txt`, `latest_version.txt`).

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
*(Note: To persist newly trained models, state updates, or pointer changes back to your local machine, map the artifacts volume: `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score`)*

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

## CLI Flags & Execution Commands

The pipeline includes built-in operational tooling to manage the machine learning lifecycle and streaming state via command-line flags.
*(Note for Docker: On Windows CMD, replace `$(pwd)` with `%cd%`)*

### Streaming & State Management

* **Standard Stream Processing**
  Reads the stream and updates the state using the currently active model.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score`
  * **Local:** `python -m src.app`

* **Replay Event Log (`--replay`)**
  It destroys the persistent state (`artifacts/state.json`) and recalculates the 30-day windows mathematically from the raw event log.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --replay`
  * **Local:** `python -m src.app --replay`

* **Time-Travel / Point-in-Time Correctness (`--time-travel`)**
  Rebuilds the state up to a specific historical ISO timestamp and evaluates the model based *only* on the data available at that exact second. (Requires `--replay`).
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --replay --time-travel "2026-05-15T10:00:00Z"`
  * **Local:** `python -m src.app --replay --time-travel "2026-05-15T10:00:00Z"`

### MLOps & Model Registry

* **Force Model Retraining (`--retrain`)**
  Triggers an offline training job before scoring. Generates new synthetic data, trains a new XGBoost version, and interactively prompts you to promote the new model to ACTIVE. *(Docker uses `-i` to allow terminal input).*
  * **Docker:** `docker run --rm -i -v $(pwd)/artifacts:/app/artifacts streaming-score --retrain`
  * **Local:** `python -m src.app --retrain`

* **Set Active Model / Promote (`--set-active-model`)**
  Administrative command to permanently update the `active_version.txt` pointer to a specific model version (example: `v_1779992085`). Exits without processing the stream. Supports the `latest` alias.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --set-active-model latest`
  * **Local:** `python -m src.app --set-active-model latest`

* **Model Rollback / Hot-Swapping (`--model-version`)**
  Temporarily bypasses the `active_version.txt` registry and forces the scoring service to load a specific historical model version for inference. Supports the `latest` alias.
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts streaming-score --model-version v_1716500000`
  * **Local:** `python -m src.app --model-version v_1716500000`

* **Custom Event Stream (`--events`)**
  Points the pipeline to a different JSONL stream file. *(Docker requires mapping the local `data/` directory).*
  * **Docker:** `docker run --rm -v $(pwd)/artifacts:/app/artifacts -v $(pwd)/data:/app/data streaming-score --events data/my_custom_events.jsonl`
  * **Local:** `python -m src.app --events data/my_custom_events.jsonl`

---

## Documentation

Refer to the `docs/` directory for system design decisions:

* **`docs/architecture.md`**:
* **`docs/reflection.md`**
