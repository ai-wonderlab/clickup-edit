"""
Celery Configuration for ClickUp Image Editor
Handles background processing with Redis
"""
from celery import Celery
import os

# Redis URL from environment or default
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Initialize Celery
celery = Celery(
    'clickup_tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery Configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Performance settings
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,
    
    # Retry settings
    task_default_retry_delay=30,  # 30 seconds
    task_max_retries=3,
    
    # Result expiration (24 hours)
    result_expires=86400,
)

# Task routes (optional - for organizing tasks)
# celery.conf.task_routes = {
#     'tasks.process_clickup_task': {'queue': 'image_processing'},
# }