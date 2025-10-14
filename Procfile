web: gunicorn app:app --timeout 120 --workers 2
worker: celery -A tasks worker --loglevel=info --concurrency=3