# System Architecture


```
=============================================================================================
                  END-TO-END STREAMING ML PIPELINE
=============================================================================================

  [ 1. INGESTION ]                [ 2. STREAM PROCESSING ]              [ 3. STATE STORE ]
+--------------------+          +--------------------------+          +--------------------+
| Real: Apache Kafka |          | Real: Apache Flink       |  R/W     | Real: AWS DynamoDB |
| Sim : events.jsonl |=========>| Sim : feature_builder.py |=========>| Sim : state.json   |
+--------------------+          +--------------------------+          +--------------------+
          |                               |                                      |
     (Raw Events)                (Calculates Windows &                   (O(1) Idempotency,
                                  Enforces Event-Time)                   Optimistic Locking)
                                          |
                                          | (Passes Pruned 30-Day Features)
                                          v
  [ 4. MODEL REGISTRY ]           [ 5. SCORING SERVICE ]                [ 6. OUTPUT SINK ]
+--------------------+          +--------------------------+          +--------------------+
| Real: S3           |  Saves/  | Real: SageMaker Endpoint |          | Real: Kafka Topic  |
| Sim : txt pointers |=========>| Sim : train_and_score.py |=========>| Sim : Terminal Out |
+--------------------+  Loads   +--------------------------+          +--------------------+
                                          |
                                  (XGBoost Inference,
                                  Predicts Fraud Prob.)

=============================================================================================
```



## 1. Kafka Topics & Message Structure

The pipeline utilizes three distinct Kafka topics:

| Topic Name | Purpose | Local Simulation |
| :--- | :--- | :--- |
| **`customer-events`** | The immutable raw input stream (source of truth). | Read from `data/events.jsonl` |
| **`feature-updates`** | Emits calculated features. Allows downstream ML teams to reuse features without recalculating them. | Passed in-memory (`feature_updates` list) |
| **`customer-scores`** | The final predictions emitted by the scoring service for business consumption. | Printed to the terminal (`stdout`) |

### Message Schema (JSON)
Each topic adheres to define schema:
**1. `customer-events` (Raw Ingestion)**
```json
{
  "event_id": "uuid-or-unique-string",
  "customer_id": "C123",
  "event_time": "2025-01-01T10:05:00Z",
  "event_type": "transaction",
  "amount": 120.50
}
```

**2. `feature-updates` (Feature Store Output)**
```json
{
  "customer_id": "C123",
  "total_transactions_30d": 5,
  "total_amount_30d": 602.50,
  "avg_amount_30d": 120.50
}
```

**3. `customer-scores` (Final Predictions)**
```json
{
  "customer_id": "C123",
  "score": 0.8942
}
```

### Message Key Strategy
All Kafka messages across all three topics are keyed by **`customer_id`**.

* **Ordering Guarantee:** Kafka only guarantees strict ordering within a single partition. Keying by `customer_id` ensures all events for a given customer route to the same partition and consumer instance. This prevents race conditions and enforces the chronological processing strictly required for accurate 30-day sliding window calculations.

### Guarantees and semantics
* **Delivery Semantics:** The system assumes **at-least-once** delivery from Kafka.
* **Duplicate Handling:** Because Kafka may redeliver messages, we enforce exact-once processing via **idempotency tracking**. The `event_id` is checked against the state store; recognized duplicates are safely ignored.
* **Ordering Strategy:** All Kafka messages are keyed by `customer_id`. Kafka guarantees strict sequential ordering within a partition. This routes all transactions for a specific customer to the exact same consumer instance, preventing race conditions and ensuring chronological window calculations.

---

## 2. State Storage (DynamoDB)

To calculate a 30-day sliding window, stateless processing is insufficient. We must store historical context using a NoSQL key-value store.

* **Partition Key:** `customer_id`
* **Sort Key:** None (Omitted). Storing the bounded event list as a single document item guarantees atomic reads/updates. I would add if if I shifted from document model to a "row-per_event" model (sort by event_time).
* **Payload:** The state stores a bounded list of recent raw events and a `latest_watermark` timestamp. This allows us to accurately drop events as they age past 30 days and handle late-arriving out-of-order data without corrupting the mathematical aggregates.
* **Concurrency:** We implement **Optimistic Concurrency Control (OCC)** using a `version` attribute to ensure simultaneous event processing does not overwrite the state.

---

## 3. Model Versioning & Deployment

The architecture decouples model training from model serving.

* **Artifact Storage:** Once trained and validated, versioned model artifacts (e.g., `model_v_1716560000.json`) are saved to an artifact registry. In production, this maps to an **AWS S3 bucket**.
* **Deployments & Rollbacks:** The scoring service dynamically loads the model version specified by environment variables or a registry pointer file. This allows infrastructure tools to instantly roll forward or roll back without requiring a code deployment or container restart.

---

## 3. Model Versioning & Deployment

* **Where the Model Artifact Lives:**
  * **Real:** Stored as serialized binaries in an **AWS S3 bucket**
  * **Simulation:** Saved locally in artifacts directory as versioned JSON files (e.g., `model_v_1716560000.json`), using `latest_version.txt` and `active_version.txt` as registry pointers.

* **Rollout & Rollback Strategy:**
  * **Real:** Handled via GitHub configuration by updating environment variables (like MODEL_VERSION) in a container orchestrator like Kubernetes. This variable acts as a runtime pointer, directing the application to pull a specific immutable artifact from S3 into memory without modifying the storage layer.
  * **Simulation:** Controlled by modifying the active pointer file or explicitly passing the `--model-version` CLI flag. This allows the scoring service to hot-swap models or instantly roll back to a known-safe version.


## 4. Replay & Backfill Strategy

Because we retain the raw `customer-events` Kafka topic and an S3 data lake, the system is fully resilient to logic changes.

### Stream-Level Replay

If feature logic changes or a model requires backtesting, the system can re-process historical events from the raw log.

* **Real:** We rewind Kafka consumer offsets to replay the historical stream through the processing engine to rebuild the DynamoDB state.
* **Sim (`--replay`):** The `--replay` flag simulates this by wiping the local `state.json` file and re-streaming the historical `events.jsonl` log from the beginning.
* **Time Travel (`--time-travel`):** Passing the `--time-travel <timestamp>` flag filters out events newer than the specified cutoff. This freezes the feature state at a specific historical millisecond, enforcing **point-in-time correctness** and preventing data leakage during backtesting.


### Large-Scale Enterprise Backfilling
Replaying a stream event-by-event might be inefficient for large-scale backfills, in such case distributed batch processing can be used:

Apache Spark or Databricks can be used to read raw historical event logs directly from S3. It would enable distributed reads. PySpark or Spark SQL would be used to process windowing and feature creation.
The iterative Python logic is translated into distributed SQL window functions (e.g., `SUM(amount) OVER (PARTITION BY customer_id ORDER BY timestamp RANGE BETWEEN INTERVAL 30 DAYS PRECEDING AND CURRENT ROW)`). The batch output is saved to the **Offline Feature Store** (like S3 or Snowflake) for Data Scientists to train future models, while the most recent state row per customer is bulk-loaded into the **Online Feature Store**  (DynamoDB). Next, the streaming app restarts with its Kafka Consumer Offset set to the offset corresponding to the timestamp where the Spark batch job finished, seamlessly resuming real-time updates.

