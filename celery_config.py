"""
Celery configuration for async task processing
"""
from celery import Celery
from config import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Celery instance
celery = Celery(
    'clickup_tasks',
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND
)

# Celery configuration
celery.conf.update(
    # Task configuration
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,  # Only fetch 1 task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to prevent memory leaks
    worker_disable_rate_limits=False,
    
    # Task execution limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    task_acks_late=True,  # Tasks acknowledged after completion
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Redis specific settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    
    # Task routing (if you want to use different queues)
    # task_routes={
    #     'tasks.process_clickup_task': {'queue': 'images'},
    #     'tasks.generate_model_prompt': {'queue': 'prompts'},
    # },
    
    # Beat schedule (if you need periodic tasks)
    beat_schedule={
        # Example: Clean up old tokens every hour
        # 'cleanup-tokens': {
        #     'task': 'tasks.cleanup_old_tokens',
        #     'schedule': 3600.0,  # Every hour
        # },
    }
)

# Import tasks to register them
# try:
#     from tasks import process_clickup_task
#     logger.info("✅ Tasks imported successfully")
# except ImportError as e:
#     logger.warning(f"⚠️ Could not import tasks: {e}")

# Optional: Configure task error handling
@celery.task(bind=True, max_retries=3)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')
    return "pong"

logger.info("✅ Celery configured successfully")