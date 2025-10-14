"""
ClickUp Image Editor - Flask App with Async Processing
Handles webhooks and queues tasks for background processing
"""
from flask import Flask, request, jsonify
import requests
import json
import time
from config import config
from tasks import process_clickup_task

app = Flask(__name__)

processed_webhooks = set()

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
    Handle incoming ClickUp webhooks
    Returns 200 immediately and queues task for background processing
    """
    try:
        data = request.json
        log(f"📥 Webhook received")
        
        # Extract task information
        task_id = data.get('task_id')
        history_items = data.get('history_items', [])
        
        # DEDUPLICATION: Check if already processed
        webhook_signature = None
        if history_items:
            webhook_signature = history_items[0].get('id')
            
            if webhook_signature and webhook_signature in processed_webhooks:
                log(f"⏭️  Duplicate webhook ignored", "WARNING")
                return jsonify({"status": "ignored", "reason": "duplicate"}), 200
        
        if not task_id:
            log("⚠️  No task_id in webhook", "WARNING")
            return jsonify({"status": "ignored", "reason": "no_task_id"}), 200
        
        # Get task details to check custom field
        task_data = get_task_details(task_id)
        if not task_data:
            return jsonify({"status": "error", "reason": "could not get task"}), 200
        
        # Check if custom field (boolean checkbox) is checked
        custom_fields = task_data.get('custom_fields', [])
        should_process = False
        user_description = task_data.get('description', '')
        
        for field in custom_fields:
            if field.get('id') == config.CLICKUP_CUSTOM_FIELD_ID:
                field_value = field.get('value')
                if field_value is True or field_value == 'true':
                    should_process = True
                    log("✅ Checkbox CHECKED - queuing task")
                    break
                else:
                    log("❌ Checkbox UNCHECKED - ignoring")
        
        if not should_process:
            return jsonify({"status": "ignored", "reason": "checkbox_not_checked"}), 200
        
        # Mark as processed
        if webhook_signature:
            processed_webhooks.add(webhook_signature)
            if len(processed_webhooks) > 1000:
                processed_webhooks.pop()
        
        # 🚀 QUEUE THE TASK FOR BACKGROUND PROCESSING
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