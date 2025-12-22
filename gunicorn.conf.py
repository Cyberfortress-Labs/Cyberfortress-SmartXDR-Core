# Gunicorn configuration for SmartXDR Core
import multiprocessing

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
# preload_app=True enables Copy-on-Write: model loads once in master, shared across workers
# This allows multiple workers WITHOUT multiplying RAM usage
workers = 2
threads = 4
worker_class = "gthread"
worker_connections = 1000
timeout = 120
keepalive = 2
preload_app = True  # Critical: load model BEFORE forking workers

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