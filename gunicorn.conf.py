import multiprocessing
import os
from gunicorn import glogging
from datetime import datetime

# --- PHẦN SỬA ĐỔI ---
class CustomLogger(glogging.Logger):
    def atoms(self, resp, req, environ, request_time):
        # Lấy các biến mặc định (atoms) từ Gunicorn
        atoms = super().atoms(resp, req, environ, request_time)
        # Ghi đè biến 't' (thời gian) bằng định dạng bạn muốn
        atoms['t'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return atoms

logger_class = CustomLogger



# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
# preload_app=True enables Copy-on-Write: model loads once in master, shared across workers
# This allows multiple workers WITHOUT multiplying RAM usage
workers = 1
threads = 8
worker_class = "gthread"
worker_connections = 1000
timeout = 120
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True

# Custom access log format to match app logs: [timestamp] [module] [level] message
access_log_format = '[%(t)s] [gunicorn.access] [INFO] %(h)s "%(r)s" %(s)s %(b)s "%(a)s"'

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