import json
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class FeatureBuilder:
    def __init__(self):
        # Simulates a DynamoDB state store. Keys are customer_ids.
        self.state = {}

    def process_event(self, event_data):
        """Processes an incoming event, handling duplicates, missing fields, and state updates."""
        try:
            # Handle both JSON strings and standard Python dictionaries
            event = json.loads(event_data) if isinstance(event_data, str) else event_data

            # Extract the required fields
            event_id = event["event_id"]
            customer_id = event["customer_id"]
            event_time_str = event["event_time"]
            amount = float(event["amount"])
        except (KeyError, ValueError, TypeError) as e:
            # If the JSON is malformed (e.g. missing 'amount'), log a warning but don't crash
            logger.warning(f"Malformed event skipped. Error: {e} | Event: {event_data}")
            return

        # Parse the ISO timestamp (Python's fromisoformat is picky about the 'Z' suffix for UTC)
        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))

        # Initialize the state for a brand new customer
        if customer_id not in self.state:
            self.state[customer_id] = {
                "processed_ids": set(),
                "events": [],
                "latest_watermark": event_time,
                "version": 1
            }

        cust_state = self.state[customer_id]

        # 1. Deduplication (Idempotency check)
        if event_id in cust_state["processed_ids"]:
            logger.info(f"Duplicate event {event_id} skipped.")
            return

        # 2. Update the state
        cust_state["processed_ids"].add(event_id)
        cust_state["events"].append({"time": event_time, "amount": amount})

        # 3. Out-of-order handling
        # Only move the watermark forward. If an old event arrives, the watermark stays the same.
        if event_time > cust_state["latest_watermark"]:
            cust_state["latest_watermark"] = event_time

        # 4. Simulate Optimistic Locking / Version Bump
        # In a real DynamoDB call, this would use: ConditionExpression="version = :expected_version"
        cust_state["version"] += 1

    def get_features(self, customer_id):
        """Computes the 30-day window features for a customer based on their state."""
        if customer_id not in self.state:
            return None

        cust_state = self.state[customer_id]

        # Calculate the boundary of our sliding window (30 days ago from our newest event)
        cutoff_time = cust_state["latest_watermark"] - timedelta(days=30)

        # 1. Pruning Phase: Keep only events that are chronologically within the 30-day window
        valid_events = [e for e in cust_state["events"] if e["time"] >= cutoff_time]

        # Update our memory store to throw away the expired events, preventing infinite growth
        cust_state["events"] = valid_events

        # 2. Calculation
        total_transactions = len(valid_events)
        total_amount = sum(e["amount"] for e in valid_events)
        avg_amount = total_amount / total_transactions if total_transactions > 0 else 0.0

        return {
            "customer_id": customer_id,
            "total_transactions_30d": total_transactions,
            "total_amount_30d": round(total_amount, 2),
            "avg_amount_30d": round(avg_amount, 2)
        }

# --- TEST  ---
if __name__ == "__main__":
    builder = FeatureBuilder()

    # Test with a mock stream
    mock_events = [
        # Standard event
        {"event_id": "1", "customer_id": "C1", "event_time": "2026-05-01T10:00:00Z", "amount": 100},
        # Another standard event
        {"event_id": "2", "customer_id": "C1", "event_time": "2026-05-15T10:00:00Z", "amount": 50},
        # DUPLICATE! Should be ignored.
        {"event_id": "2", "customer_id": "C1", "event_time": "2026-05-15T10:00:00Z", "amount": 50},
        # OUT OF ORDER! This arrived late, but belongs in the window.
        {"event_id": "3", "customer_id": "C1", "event_time": "2026-05-05T10:00:00Z", "amount": 25},
        # MALFORMED! Missing amount. Should log warning but not crash.
        {"event_id": "4", "customer_id": "C1", "event_time": "2026-05-20T10:00:00Z"},
        # OLD EVENT! 31 days older than the newest event (May 15). Should be pruned.
        {"event_id": "5", "customer_id": "C1", "event_time": "2026-04-10T10:00:00Z", "amount": 1000},
    ]

    print("--- Processing Events ---")
    for event in mock_events:
        builder.process_event(event)

    print("\n--- Final Features ---")
    print(builder.get_features("C1"))
