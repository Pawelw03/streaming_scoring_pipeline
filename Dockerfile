FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/ ./data/
# Note: In a real production setup, I would not copy the model artifacts into the container. Instead, the scoring service would load them from an external artifact registry (e.g., S3) at runtime.
COPY artifacts/ ./artifacts/

# Set the default command to run the pipeline using CLI
# (This naturally picks up data/events.jsonl as defined in app.py default)
ENTRYPOINT ["python", "-m", "src.app"]
