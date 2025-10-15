"""
ClickUp Image Editor - Flask App with Async Processing
Handles webhooks and queues tasks for background processing
"""
from flask import Flask, request, jsonify
import requests
import json
import time
import redis
from config import config
from tasks import process_clickup_task

app = Flask(__name__)

# Initialize Redis client for deduplication and locking
redis_client = redis.from_url(config.REDIS_URL)

def log(message, level="INFO"):
    """Simple logging function"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def get_clickup_headers():
    """Get ClickUp API headers"""
    return {
        "Authorization": config.CLICKUP_API_TOKEN,
        "Content-Type": "application/json"
    }

def get_task_details(task_id):
    """Get task details from ClickUp"""
    try:
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}"
        response = requests.get(url, headers=get_clickup_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"Error getting task details: {e}", "ERROR")
        return None

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """
    Handle incoming ClickUp webhooks with Redis-based deduplication and locking
    Returns 200 immediately and queues task for background processing
    """
    try:
        data = request.json
        log(f"📥 Webhook received")
        
        # 1️⃣ WEBHOOK-LEVEL DEDUPLICATION
        webhook_id = data.get('webhook_id')
        if webhook_id:
            dedup_key = f"webhook:{webhook_id}"
            if redis_client.get(dedup_key):
                log("⏭️ Duplicate webhook ignored", "WARNING")
                return jsonify({"status": "duplicate"}), 200
            # Mark webhook as processed (expires in 60 seconds)
            redis_client.setex(dedup_key, 60, "processed")
        
        # 2️⃣ CHECK EVENT TYPE
        event = data.get('event')
        if event != 'taskUpdated':
            log("⏭️ Non-update event ignored", "INFO")
            return jsonify({"status": "ignored", "reason": "not_task_update"}), 200
        
        # 3️⃣ EXTRACT TASK INFORMATION
        task_id = data.get('task_id')
        history_items = data.get('history_items', [])
        
        if not task_id:
            log("⚠️ No task_id in webhook", "WARNING")
            return jsonify({"status": "ignored", "reason": "no_task_id"}), 200
        
        if not history_items:
            log("⚠️ No history items", "WARNING")
            return jsonify({"status": "ignored", "reason": "no_history"}), 200
        
        # 4️⃣ GET TASK DETAILS AND CHECK CUSTOM FIELD
        task_data = get_task_details(task_id)
        if not task_data:
            return jsonify({"status": "error", "reason": "could not get task"}), 200
        
        custom_fields = task_data.get('custom_fields', [])
        should_process = False
        user_description = task_data.get('description', '')
        
        for field in custom_fields:
            if field.get('id') == config.CLICKUP_CUSTOM_FIELD_ID:
                field_value = field.get('value')
                if field_value is True or field_value == 'true':
                    should_process = True
                    log("✅ Checkbox CHECKED - proceeding")
                    break
                else:
                    log("❌ Checkbox UNCHECKED - ignoring")
        
        if not should_process:
            return jsonify({"status": "ignored", "reason": "checkbox_not_checked"}), 200
        
        # 5️⃣ TASK-LEVEL LOCKING (prevent duplicate processing)
        lock_key = f"task_lock:{task_id}"
        
        if redis_client.get(lock_key):
            log("🔒 Task already processing - ignoring", "WARNING")
            return jsonify({"status": "already_running"}), 200
        
        # Set lock (expires in 10 minutes = 600 seconds)
        redis_client.setex(lock_key, 600, "locked")
        
        # 6️⃣ QUEUE THE TASK FOR BACKGROUND PROCESSING
        task = process_clickup_task.delay(task_id, user_description)
        
        log(f"🎯 Task queued: {task.id}")
        
        # Return immediately!
        return jsonify({
            "status": "queued",
            "task_id": task_id,
            "celery_task_id": task.id,
            "message": "Task queued for processing"
        }), 200
        
    except Exception as e:
        log(f"Error handling webhook: {e}", "ERROR")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "config_loaded": bool(config.CLICKUP_API_TOKEN and config.OPENROUTER_API_KEY and config.WAVESPEED_API_KEY)
    }), 200

@app.route('/task/status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Check status of a Celery task"""
    try:
        from celery.result import AsyncResult
        task = AsyncResult(task_id)
        
        response = {
            "task_id": task_id,
            "state": task.state,
            "ready": task.ready(),
        }
        
        if task.ready():
            response["result"] = task.result
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/test', methods=['POST'])
def test_endpoint():
    """Test endpoint for manual testing"""
    try:
        data = request.json
        task_id = data.get('task_id')
        description = data.get('description', 'make it beautiful')
        
        if not task_id:
            return jsonify({"error": "task_id required"}), 400
        
        # Queue the task
        task = process_clickup_task.delay(task_id, description)
        
        return jsonify({
            "status": "queued",
            "celery_task_id": task.id
        }), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    
    log("="*60)
    log("🚀 ClickUp AI Workflow Server Starting...")
    log("="*60)
    log(f"Mode: Background Processing with Celery")
    log(f"Port: {config.FLASK_PORT}")
    log("="*60)
    
    port = int(os.environ.get('PORT', config.FLASK_PORT))
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=config.FLASK_DEBUG
    )