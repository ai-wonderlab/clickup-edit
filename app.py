from flask import Flask, request, jsonify
import requests
import base64
import os
import json
import time
from io import BytesIO
from PIL import Image
from config import config

app = Flask(__name__)

processed_webhooks = set()

# Load activation guide and deep research
def load_activation_guide():
    try:
        with open('activation_guide.txt', 'r') as f:
            return f.read()
    except Exception as e:
        log(f"Warning: Could not load activation_guide.txt: {e}", "WARNING")
        return ""

def load_deep_research():
    try:
        with open('deep_research.txt', 'r') as f:
            return f.read()
    except Exception as e:
        log(f"Warning: Could not load deep_research.txt: {e}", "WARNING")
        return ""

ACTIVATION_GUIDE = load_activation_guide()
DEEP_RESEARCH = load_deep_research()

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

def get_task_attachments(task_id):
    """Get attachments from a ClickUp task"""
    try:
        task_data = get_task_details(task_id)
        if not task_data:
            return []
        
        attachments = task_data.get('attachments', [])
        return attachments
    except Exception as e:
        log(f"Error getting attachments: {e}", "ERROR")
        return []

def download_image(image_url):
    """Download image from URL and return as bytes"""
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        log(f"Error downloading image: {e}", "ERROR")
        return None

def format_prompt_with_gemini(user_description):
    """Format user description into optimized prompt using Gemini with extended thinking"""
    try:
        # Construct system prompt: Activation + Deep Research
        system_prompt = f"""{ACTIVATION_GUIDE}

{DEEP_RESEARCH}"""
        
        # User message: Just the description
        user_message = f"""USER DESCRIPTION: {user_description}

Think deeply about this vision and translate it into the perfect SeaDream v4 prompt.

OUTPUT (optimized SeaDream v4 prompt only):"""

        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://clickup-ai-workflow.app",
            "X-Title": "ClickUp AI Image Editor"
        }
        
        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "temperature": 0.7,
            "max_tokens": 2000,  # Extended output for detailed prompts
            "top_p": 0.95,
            # Enable thinking/reasoning mode
            "reasoning_effort": config.GEMINI_THINKING_MODE,  # Options: low, medium, high
            "stream": False  # Ensure we wait for complete response
        }
        
        log("Sending prompt to Gemini 2.5 Pro (with extended thinking)...")
        log("⏳ Waiting for Gemini to process (this may take 30-60 seconds)...")
        
        start_time = time.time()
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120  # 2 minutes timeout for thinking mode
        )
        response.raise_for_status()
        
        elapsed = time.time() - start_time
        log(f"✅ Gemini processing completed in {elapsed:.1f} seconds")
        
        result = response.json()
        
        # Log usage stats if available
        if 'usage' in result:
            usage = result['usage']
            log(f"📊 Tokens used - Prompt: {usage.get('prompt_tokens', 'N/A')}, "
                f"Completion: {usage.get('completion_tokens', 'N/A')}")
        
        formatted_prompt = result['choices'][0]['message']['content'].strip()
        
        # Clean any markdown or prefixes
        formatted_prompt = formatted_prompt.replace('```', '').strip()
        if formatted_prompt.startswith('OUTPUT'):
            formatted_prompt = formatted_prompt.split(':', 1)[1].strip()
        if formatted_prompt.startswith('OPTIMIZED'):
            formatted_prompt = formatted_prompt.split(':', 1)[1].strip()
        
        # Log preview of the prompt
        log(f"🎨 Gemini 2.5 Pro optimized prompt preview:")
        log(f"   {formatted_prompt[:200]}{'...' if len(formatted_prompt) > 200 else ''}")
        
        return formatted_prompt
        
    except requests.exceptions.Timeout:
        log(f"⏱️ Gemini request timed out after 120 seconds", "ERROR")
        log("Using original description as fallback", "WARNING")
        return user_description
    except Exception as e:
        log(f"Error formatting prompt with Gemini: {e}", "ERROR")
        log("Using original description as fallback", "WARNING")
        return user_description

def edit_image_with_seedream(image_bytes, prompt):
    """Send image to SeaDream v4 for editing"""
    try:
        # Convert image bytes to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {config.WAVESPEED_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "image": image_base64,
            "prompt": prompt,
            "negative_prompt": "low quality, blurry, distorted, ugly, deformed",
            "num_inference_steps": 30,
            "guidance_scale": 7.5
        }
        
        log(f"Sending image to SeaDream v4 for editing...")
        response = requests.post(
            config.WAVESPEED_API_URL,
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        
        # WaveSpeed API is async - get the prediction ID
        if result.get('code') == 200 and 'data' in result:
            data = result['data']
            prediction_id = data.get('id')
            get_url = data.get('urls', {}).get('get')
            
            if not get_url:
                log("No GET URL in response", "ERROR")
                return None
            
            log(f"Job created: {prediction_id}. Polling for result...")
            
            # Poll for result (max 2 minutes)
            max_attempts = 60  # 60 attempts * 2 seconds = 2 minutes
            for attempt in range(max_attempts):
                time.sleep(2)  # Wait 2 seconds between polls
                
                log(f"Polling attempt {attempt + 1}/{max_attempts}...")
                poll_response = requests.get(get_url, headers=headers)
                poll_response.raise_for_status()
                poll_result = poll_response.json()
                
                if poll_result.get('code') == 200 and 'data' in poll_result:
                    poll_data = poll_result['data']
                    status = poll_data.get('status')
                    
                    log(f"Status: {status}")
                    
                    if status == 'completed':
                        outputs = poll_data.get('outputs', [])
                        if outputs and len(outputs) > 0:
                            # Get the first output image URL
                            output_url = outputs[0]
                            log(f"Image ready! Downloading from: {output_url}")
                            
                            # Download the edited image
                            img_response = requests.get(output_url)
                            img_response.raise_for_status()
                            edited_image_bytes = img_response.content
                            
                            log("SeaDream v4 editing completed successfully")
                            return edited_image_bytes
                        else:
                            log("No outputs in completed result", "ERROR")
                            return None
                    
                    elif status == 'failed':
                        error = poll_data.get('error', 'Unknown error')
                        log(f"SeaDream job failed: {error}", "ERROR")
                        return None
            
            log("Timeout waiting for SeaDream result", "ERROR")
            return None
        else:
            log(f"Unexpected response format from SeaDream: {result}", "ERROR")
            return None
            
    except Exception as e:
        log(f"Error editing image with SeaDream: {e}", "ERROR")
        return None

def upload_image_to_clickup(task_id, image_bytes, filename="edited_image.png"):
    """Upload edited image to ClickUp task"""
    try:
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/attachment"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN
        }
        
        files = {
            'attachment': (filename, image_bytes, 'image/png')
        }
        
        log(f"Uploading edited image to ClickUp task {task_id}...")
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        
        log("Image uploaded successfully to ClickUp")
        return True
        
    except Exception as e:
        log(f"Error uploading image to ClickUp: {e}", "ERROR")
        return False

def update_custom_field(task_id, checked=False):
    """Update boolean custom field (uncheck after processing)"""
    try:
        status = "CHECKED ✅" if checked else "UNCHECKED ❌"
        log(f"Updating boolean field to: {status}")
        
        url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{config.CLICKUP_CUSTOM_FIELD_ID}"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        payload = {
            "value": checked  # true or false
        }
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        log(f"Boolean field updated successfully to: {status}")
        return True
        
    except Exception as e:
        log(f"Error updating boolean field: {e}", "ERROR")
        return False

def process_task(task_id, user_description):
    """Main processing function for a task"""
    log(f"Starting processing for task {task_id}")
    
    # Step 1: Get task attachments
    log("Step 1: Getting task attachments...")
    attachments = get_task_attachments(task_id)
    if not attachments:
        log("No attachments found in task", "ERROR")
        return False
    
    # Get the first image attachment
    image_url = None
    for attachment in attachments:
        if attachment.get('mimetype', '').startswith('image/'):
            image_url = attachment.get('url')
            break
    
    if not image_url:
        log("No image attachment found", "ERROR")
        return False
    
    log(f"Found image: {image_url}")
    
    # Step 2: Download image
    log("Step 2: Downloading image...")
    image_bytes = download_image(image_url)
    if not image_bytes:
        return False
    
    # Step 3: Format prompt with Gemini
    log("Step 3: Formatting prompt with Gemini...")
    formatted_prompt = format_prompt_with_gemini(user_description)
    
    # Step 4: Edit image with SeaDream v4
    log("Step 4: Editing image with SeaDream v4...")
    edited_image_bytes = edit_image_with_seedream(image_bytes, formatted_prompt)
    if not edited_image_bytes:
        return False
    
    # Step 5: Upload edited image back to ClickUp
    log("Step 5: Uploading edited image to ClickUp...")
    upload_success = upload_image_to_clickup(task_id, edited_image_bytes)
    if not upload_success:
        return False
    
    # Step 6: Update custom field to mark as complete
    log("Step 6: Updating custom field...")
    update_custom_field(task_id, checked=False)

    
    log("✅ Processing completed successfully!", "SUCCESS")
    return True

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Handle incoming ClickUp webhooks"""
    try:
        data = request.json
        log(f"Received webhook: {json.dumps(data, indent=2)}")
        
        # Extract task information
        event = data.get('event')
        task_id = data.get('task_id')
        
        # DEDUPLICATION: Check if we've already processed this exact webhook
        webhook_signature = None
        history_items = data.get('history_items', [])
        if history_items:
            # Use the history item ID as unique identifier
            webhook_signature = history_items[0].get('id')
            
            if webhook_signature and webhook_signature in processed_webhooks:
                log(f"Duplicate webhook detected (ID: {webhook_signature}), ignoring", "WARNING")
                return jsonify({"status": "ignored", "reason": "duplicate"}), 200
        
        if not task_id:
            log("No task_id in webhook", "WARNING")
            return jsonify({"status": "ignored", "reason": "no task_id"}), 200
        
        # Get task details to check custom field
        task_data = get_task_details(task_id)
        if not task_data:
            return jsonify({"status": "error", "reason": "could not get task details"}), 200
        
        # Check if custom field (boolean checkbox) is checked
        custom_fields = task_data.get('custom_fields', [])
        should_process = False
        user_description = task_data.get('description', '')
        
        for field in custom_fields:
            if field.get('id') == config.CLICKUP_CUSTOM_FIELD_ID:
                field_value = field.get('value')
                # Boolean field: true = checked = process
                if field_value is True or field_value == 'true':
                    should_process = True
                    log("✅ Boolean field is CHECKED - starting processing")
                    break
                else:
                    log("❌ Boolean field is UNCHECKED - ignoring")
        
        if not should_process:
            log("Custom field not set to trigger value, ignoring", "INFO")
            return jsonify({"status": "ignored", "reason": "custom field not set"}), 200
        
        # Mark this webhook as processed BEFORE starting the long process
        if webhook_signature:
            processed_webhooks.add(webhook_signature)
            # Keep only last 1000 to prevent memory issues
            if len(processed_webhooks) > 1000:
                # Remove oldest item (first item in set)
                processed_webhooks.pop()
        
        # Process the task
        success = process_task(task_id, user_description)
        
        if success:
            return jsonify({"status": "success", "task_id": task_id}), 200
        else:
            return jsonify({"status": "error", "task_id": task_id}), 200
        
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

@app.route('/test', methods=['POST'])
def test_endpoint():
    """Test endpoint for manual testing"""
    try:
        data = request.json
        task_id = data.get('task_id')
        description = data.get('description', 'make it beautiful')
        
        if not task_id:
            return jsonify({"error": "task_id required"}), 400
        
        success = process_task(task_id, description)
        
        if success:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    log("="*60)
    log("ClickUp AI Workflow Server Starting...")
    log("="*60)
    log(f"Flask Debug Mode: {config.FLASK_DEBUG}")
    log(f"Port: {config.FLASK_PORT}")
    log(f"Activation Guide Loaded: {'True' if ACTIVATION_GUIDE else 'False'}")
    log(f"Deep Research Loaded: {'True' if DEEP_RESEARCH else 'False'}")
    log("="*60)
    
    # Get port from environment (Railway sets this)
    port = int(os.environ.get('PORT', config.FLASK_PORT))
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=config.FLASK_DEBUG
    )