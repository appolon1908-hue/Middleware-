from prometheus_client import Counter, Gauge, Histogram

ACK = Histogram("codestra_fast_ack_seconds", "Fast ACK total latency")
DB_COMMIT = Histogram("codestra_db_commit_seconds", "Ingress commit latency")
AUTH_FAILURES = Counter("codestra_auth_failures_total", "Authentication failures", ["kind"])
SCHEMA_REJECTIONS = Counter("codestra_schema_rejections_total", "Schema rejections")
IDEMPOTENT_REPLAYS = Counter("codestra_idempotent_replays_total", "Idempotent replays")
IDEMPOTENCY_CONFLICTS = Counter("codestra_idempotency_conflicts_total", "Idempotency conflicts")
QUEUE_DEPTH = Gauge("codestra_delivery_queue_depth", "Delivery queue depth", ["target", "status"])
OLDEST_AGE = Gauge("codestra_delivery_oldest_seconds", "Oldest delivery age", ["target"])
DLQ_DEPTH = Gauge("codestra_dlq_depth", "Dead-letter queue depth", ["target"])
RECONCILIATION_GAPS = Gauge("codestra_reconciliation_gaps", "Report-only reconciliation gaps", ["category"])
