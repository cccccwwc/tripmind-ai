import os


# Configuration is read while application modules are imported.  Tests never
# send these placeholder values to an external service.
os.environ.setdefault("AMAP_API_KEY", "test-amap-key")
os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("LLM_BASE_URL", "https://example.invalid/v1")
os.environ.setdefault("LLM_MODEL_ID", "test-model")
