"""
Main Flask application for ClickUp webhook handling
"""
from flask import Flask, request, jsonify, send_file, abort
import logging
import redis
import time
from celery_config import celery
from config import config
from tasks import process_clickup_task
from proxy_storage import get_proxy_token_data
import json
import requests
import io
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis client for deduplication
redis_client = redis.from_url(config.REDIS_URL)

@app.route('/proxy/image/<token>')
def serve_image(token):
    """Serve image through proxy with CORS and ngrok support"""
    logger.info(f"🔍 PROXY REQUEST: Token={token[:8]}... from IP={request.remote_addr}")
    
    # Get token data from Redis
    token_data = get_proxy_token_data(token)
    
    if not token_data:
        logger.warning(f"❌ Invalid/expired token: {token[:8]}...")
        abort(404, "Invalid or expired token")
    
    # Check if manually expired (Redis TTL handles this, but double-check)
    if 'expires' in token_data and datetime.now() > token_data['expires']:
        logger.warning(f"❌ Token expired: {token[:8]}...")
        abort(404, "Token expired")
    
    logger.info(f"✅ Token valid, fetching from: {token_data['url'][:50]}...")
    
    try:
        # Fetch from source with auth
        headers = {}
        if 'clickup' in token_data['url'].lower():
            headers = {"Authorization": config.CLICKUP_API_TOKEN}
        
        response = requests.get(
            token_data['url'], 
            headers=headers, 
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"❌ Source returned {response.status_code}")
            abort(response.status_code)
        
        # Determine content type
        content_type = content_type = 'image/png'

        logger.info(f"✅ Serving {len(response.content)} bytes as {content_type}")
        
        # Create response with CORS headers
        file_response = send_file(
            io.BytesIO(response.content),
            mimetype=content_type,
            as_attachment=False,
            download_name=f"image_{token[:8]}.png"
        )
        
        # Add CORS headers for Claude API access
        file_response.headers['Access-Control-Allow-Origin'] = '*'
        file_response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        file_response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        
        # Bypass ngrok browser warning
        file_response.headers['ngrok-skip-browser-warning'] = 'true'
        
        return file_response
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout fetching image for {token[:8]}...")
        abort(504, "Gateway timeout")
    except Exception as e:
        logger.error(f"❌ Error serving image: {e}")
        abort(500, str(e))

@app.route('/proxy/image/<token>', methods=['OPTIONS'])
def serve_image_options(token):
    """Handle preflight CORS requests"""
    response = jsonify({"status": "ok"})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/webhook/clickup', methods=['POST'])
def clickup_webhook():
    """Handle ClickUp webhook for custom field changes"""
    try:
        data = request.json
        
        # Extract webhook data
        webhook_id = data.get('webhook_id')
        event = data.get('event')
        task_id = data.get('task_id')
        
        logger.info(f"📨 Webhook received: {event} for task {task_id}")
        
        # Only process taskUpdated events
        if event != 'taskUpdated':
            return jsonify({"status": "ignored", "reason": "not_task_update"}), 200
        
        # Check if it's our custom checkbox
        history_items = data.get('history_items', [])
        
        for item in history_items:
            field = item.get('field')
            
            # Check if it's a custom field change
            if field == 'custom_field':
                custom_field_data = item.get('custom_field', {})
                custom_field_id = custom_field_data.get('id')
                
                # Check if it's OUR custom field
                if custom_field_id == config.CLICKUP_CUSTOM_FIELD_ID:
                    after_value = item.get('after')
                    
                    # Check if checkbox was checked (string "true")
                    if after_value == "true":
                        # Implement deduplication with Redis
                        lock_key = f"task_lock:{task_id}"
                        
                        # Try to acquire lock (expires in 5 minutes)
                        if redis_client.set(lock_key, "processing", nx=True, ex=300):
                            logger.info(f"🔒 Lock acquired for task {task_id}")
                            
                            # FIXED: Fetch full task data from ClickUp API
                            description = get_task_description_from_api(task_id)
                            
                            if not description:
                                logger.error(f"❌ No description found for task {task_id}")
                                redis_client.delete(lock_key)
                                return jsonify({
                                    "status": "error",
                                    "reason": "no_description"
                                }), 400
                            
                            logger.info(f"📝 Description: {description[:100]}...")
                            
                            # Queue the task
                            task = process_clickup_task.delay(task_id, description)
                            logger.info(f"✅ Task queued: {task.id}")
                            
                            return jsonify({
                                "status": "queued",
                                "task_id": task_id,
                                "celery_task_id": task.id
                            }), 200
                        else:
                            logger.warning(f"⚠️ Task {task_id} already being processed")
                            return jsonify({
                                "status": "duplicate",
                                "reason": "already_processing"
                            }), 200
        
        return jsonify({"status": "ignored", "reason": "not_our_checkbox"}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

def get_task_description_from_api(task_id):
    """Fetch task description from ClickUp API"""
    try:
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}"
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        task_data = response.json()
        
        # Try to get description from task
        description = task_data.get('description', '')
        
        # If no description, check if there's a custom text field with instructions
        if not description:
            custom_fields = task_data.get('custom_fields', [])
            for field in custom_fields:
                # Look for a text field that might contain editing instructions
                if field.get('type') == 'text' and field.get('value'):
                    description = field['value']
                    break
        
        # If still no description, use task name as last resort
        if not description:
            description = task_data.get('name', '')
        
        return description.strip()
        
    except Exception as e:
        logger.error(f"❌ Error fetching task description: {e}")
        return ""

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check Redis
        redis_client.ping()
        redis_status = "connected"
    except:
        redis_status = "disconnected"
    
    # Check Celery
    try:
        stats = celery.control.inspect().stats()
        celery_status = "connected" if stats else "disconnected"
    except:
        celery_status = "disconnected"
    
    # Get proxy stats
    from proxy_storage import get_proxy_stats
    proxy_stats = get_proxy_stats()
    
    return jsonify({
        "status": "healthy",
        "redis": redis_status,
        "celery": celery_status,
        "proxy": proxy_stats,
        "timestamp": time.time()
    })

@app.route('/', methods=['GET'])
def index():
    """Basic info endpoint"""
    return jsonify({
        "service": "ClickUp Image Processing",
        "version": "2.0",
        "endpoints": {
            "/webhook/clickup": "ClickUp webhook endpoint",
            "/proxy/image/<token>": "Proxy image endpoint",
            "/health": "Health check",
            "/": "This page"
        }
    })

if __name__ == '__main__':
    # Validate configuration
    config.validate()
    
    port = int(config.FLASK_PORT)
    logger.info(f"🚀 Starting Flask app on port {port}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=config.DEBUG
    )