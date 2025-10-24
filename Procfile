web: gunicorn app:app --timeout 120 --workers 2
worker: celery -A celery_config worker --loglevel=info --concurrency=3
proxy: gunicorn proxy_server:app --bind 0.0.0.0:5001 --timeout 120