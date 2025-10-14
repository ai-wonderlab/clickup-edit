"""
Celery Tasks for ClickUp Image Processing
Handles async background processing
"""
from celery_config import celery
from file_converters import convert_to_png
import requests
import base64
import time
import logging
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log(message, level="INFO"):
    """Simple logging function"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] [{level}] {message}")

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

def download_file(file_url):
    """Download file from URL and return as bytes"""
    try:
        response = requests.get(file_url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        log(f"Error downloading file: {e}", "ERROR")
        return None

def format_prompt_with_gemini(user_description):
    """Format user description into optimized prompt using Gemini"""
    try:
        # Load prompts
        try:
            with open('activation_guide.txt', 'r') as f:
                activation_guide = f.read()
        except:
            activation_guide = ""
            
        try:
            with open('deep_research.txt', 'r') as f:
                deep_research = f.read()
        except:
            deep_research = ""
        
        system_prompt = f"""{activation_guide}

{deep_research}"""
        
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
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 0.95,
            "stream": False
        }
        
        log("Sending prompt to Gemini 2.5 Pro...")
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        formatted_prompt = result['choices'][0]['message']['content'].strip()
        
        log(f"✅ Gemini optimized prompt: {formatted_prompt[:100]}...")
        return formatted_prompt
        
    except Exception as e:
        log(f"Error with Gemini: {e}", "ERROR")
        return user_description

def edit_image_with_seedream(image_bytes, prompt, size="2048*2048"):
    """Send image to SeaDream v4 for editing"""
    try:
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {config.WAVESPEED_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "images": [image_base64],
            "prompt": prompt,
            "size": size,
            "enable_sync_mode": False,
            "enable_base64_output": False
        }
        
        log(f"Sending to SeaDream v4 (size: {size})...")
        
        response = requests.post(
            "https://api.wavespeed.ai/api/v3/bytedance/seedream-v4/edit",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('code') == 200 and 'data' in result:
            data = result['data']
            prediction_id = data.get('id')
            get_url = data.get('urls', {}).get('get')
            
            log(f"Job created: {prediction_id}")
            
            # Poll for result
            max_attempts = 60
            for attempt in range(max_attempts):
                time.sleep(2)
                
                poll_response = requests.get(get_url, headers=headers)
                poll_response.raise_for_status()
                poll_result = poll_response.json()
                
                if poll_result.get('code') == 200 and 'data' in poll_result:
                    poll_data = poll_result['data']
                    status = poll_data.get('status')
                    
                    if status == 'completed':
                        outputs = poll_data.get('outputs', [])
                        if outputs:
                            output_url = outputs[0]
                            img_response = requests.get(output_url)
                            img_response.raise_for_status()
                            log("✅ SeaDream completed")
                            return img_response.content
                    elif status == 'failed':
                        log(f"SeaDream failed: {poll_data.get('error')}", "ERROR")
                        return None
            
            log("Timeout waiting for SeaDream", "ERROR")
            return None
        else:
            log(f"Unexpected SeaDream response", "ERROR")
            return None
            
    except Exception as e:
        log(f"Error with SeaDream: {e}", "ERROR")
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
        
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        
        log(f"✅ Uploaded: {filename}")
        return True
        
    except Exception as e:
        log(f"Error uploading: {e}", "ERROR")
        return False

def update_custom_field(task_id, checked=False):
    """Update boolean custom field"""
    try:
        url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{config.CLICKUP_CUSTOM_FIELD_ID}"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json={"value": checked})
        response.raise_for_status()
        
        log(f"✅ Field updated: {'CHECKED' if checked else 'UNCHECKED'}")
        return True
        
    except Exception as e:
        log(f"Error updating field: {e}", "ERROR")
        return False

@celery.task(bind=True, max_retries=3)
def process_clickup_task(self, task_id, user_description):
    """
    Main Celery task for processing ClickUp tasks
    Runs in background worker, handles multiple file formats
    """
    try:
        log(f"🚀 Starting task {task_id} (Worker: {self.request.hostname})")
        
        # Get attachments
        attachments = get_task_attachments(task_id)
        if not attachments:
            log("No attachments found", "ERROR")
            return {"status": "error", "reason": "no_attachments"}
        
        # Find first supported file
        file_url = None
        filename = None
        for attachment in attachments:
            fname = attachment.get('title', '')

            # 🔧 SKIP files we created (prevent recursive loop)
            if fname.startswith('edited_'):
                continue

            if any(fname.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.psd', '.gif', '.bmp']):
                file_url = attachment.get('url')
                filename = fname
                break
        
        if not file_url:
            log("No supported file found", "ERROR")
            return {"status": "error", "reason": "unsupported_format"}
        
        log(f"Found file: {filename}")
        
        # Download file
        file_bytes = download_file(file_url)
        if not file_bytes:
            return {"status": "error", "reason": "download_failed"}
        
        # Convert to PNG if needed
        log("Converting file to PNG...")
        image_bytes = convert_to_png(file_bytes, filename)
        if not image_bytes:
            return {"status": "error", "reason": "conversion_failed"}
        
        # Format prompt with Gemini
        log("Optimizing prompt with Gemini...")
        formatted_prompt = format_prompt_with_gemini(user_description)
        
        # Check if dual aspect ratio needed
        needs_dual = any(keyword in user_description.lower() for keyword in ['9:16', '9x16', 'διαστάσεις', 'stories'])
        
        # 🔧 UNCHECK FIELD FIRST - BEFORE UPLOADING!
        update_custom_field(task_id, checked=False)
        log("✅ Checkbox unchecked - now uploading images...")

        if needs_dual:
            log("📐 Dual aspect ratio detected - generating 2 versions")
            
            # Generate 9:16 Stories version
            log("Editing 9:16 Stories version...")
            edited_story = edit_image_with_seedream(image_bytes, formatted_prompt, size="1088*1920")
            if edited_story:
                upload_image_to_clickup(task_id, edited_story, "edited_story_9x16.png")
            
            # Generate 1:1 Feed version
            log("Editing 1:1 Feed version...")
            edited_feed = edit_image_with_seedream(image_bytes, formatted_prompt, size="1408*1408")
            if edited_feed:
                upload_image_to_clickup(task_id, edited_feed, "edited_feed_1x1.png")
        else:
            # Single version
            log("Editing single version...")
            edited_image = edit_image_with_seedream(image_bytes, formatted_prompt)
            if edited_image:
                upload_image_to_clickup(task_id, edited_image, "edited_image.png")
        
        log("✅ Task completed successfully!", "SUCCESS")
        return {"status": "success", "task_id": task_id}
        
    except Exception as e:
        log(f"Task failed: {e}", "ERROR")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))