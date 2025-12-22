# Gunicorn configuration for SmartXDR Core
import multiprocessing

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
# Use 1 worker to avoid loading CrossEncoder model multiple times (saves ~500MB RAM per worker)
# Threads handle concurrency within the single worker
workers = 1
threads = 4
worker_class = "gthread"
worker_connections = 1000
timeout = 120
keepalive = 2

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True

# Process naming
proc_name = "smartxdr_gunicorn"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190