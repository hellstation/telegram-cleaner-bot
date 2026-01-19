from prometheus_client import CollectorRegistry, Counter, Histogram

# Prometheus metrics
registry = CollectorRegistry()
messages_processed = Counter('telegram_messages_processed_total', 'Total messages processed', registry=registry)
commands_processed = Counter('telegram_commands_processed_total', 'Total commands processed', ['command'], registry=registry)
errors_total = Counter('telegram_errors_total', 'Total errors', ['type'], registry=registry)
processing_time = Histogram('telegram_message_processing_duration_seconds', 'Message processing time', registry=registry)
files_processed = Counter('telegram_files_processed_total', 'Total files processed', registry=registry)
