import os
import gevent.monkey
gevent.monkey.patch_all()

bind = "0.0.0.0:1236"
workers = 4
worker_class = "gevent"
worker_connections = 1000 
timeout = 30
graceful_timeout = 15
keepalive = 5

max_requests = 1000
max_requests_jitter = 50

def worker_exit(server, worker):  # pyright: ignore[]
    try:
        os._exit(0)
    except:
        pass
    exit()
        