"""
Celery Tasks for ClickUp Image Processing
Handles async background processing with 6 AI models
"""
from celery_config import celery
from file_converters import convert_to_png
import requests
import base64
import time
import logging
import redis
from config import config
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import os

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

def create_image_edit_job(image_url, prompt, width, height, endpoint, model_name):
    """Create image editing job - supports all 6 models with correct payloads"""
    try:
        headers = {
            'Authorization': f'Bearer {config.WAVESPEED_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Build payload based on model
        if 'seedream' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'size': f'{width}*{height}',
                'enable_sync_mode': False,
                'enable_base64_output': False
            }
        elif 'qwen-image/edit-plus' in endpoint:
            payload = {
                'enable_base64_output': False,
                'enable_sync_mode': False,
                'images': [image_url],
                'output_format': 'png',
                'prompt': prompt,
                'seed': -1,
                'size': f'{width}*{height}'
            }
        elif 'wan-2.5' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'seed': -1,
                'size': f'{width}*{height}'
            }
        elif 'qwen-image/edit-lora' in endpoint:
            payload = {
                'enable_base64_output': False,
                'enable_sync_mode': False,
                'image': image_url,
                'loras': [],
                'output_format': 'png',
                'prompt': prompt,
                'seed': -1
            }
        elif 'nano-banana' in endpoint:
            # Nano Banana uses aspect_ratio, not size
            aspect = "1:1" if width == height else "9:16"
            payload = {
                'aspect_ratio': aspect,
                'enable_base64_output': False,
                'enable_sync_mode': False,
                'images': [image_url],
                'output_format': 'png',
                'prompt': prompt
            }
        else:  # qwen-image/edit (base)
            payload = {
                'enable_base64_output': False,
                'enable_sync_mode': False,
                'image': image_url,
                'output_format': 'png',
                'prompt': prompt,
                'seed': -1
            }
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract job ID
        if 'data' in data:
            return data['data'].get('id'), data['data'].get('urls', {}).get('get')
        elif 'requestId' in data:
            return data['requestId'], None
        
        return None, None
        
    except Exception as e:
        log(f"Error creating job for {model_name}: {str(e)}", level='ERROR')
        return None, None

def poll_for_result(job_id, endpoint, get_url=None, max_attempts=60, interval=2):
    """Poll for job result"""
    try:
        headers = {
            'Authorization': f'Bearer {config.WAVESPEED_API_KEY}'
        }
        
        # Build status URL
        if get_url:
            status_url = get_url
        else:
            status_url = f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(status_url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # Handle different response structures
                if 'data' in data:
                    status = data['data'].get('status')
                    if status == 'completed':
                        outputs = data['data'].get('outputs', [])
                        if outputs:
                            return outputs[0]
                    elif status == 'failed':
                        return None
                else:
                    status = data.get('status')
                    if status == 'completed' or status == 'succeeded':
                        return data.get('output') or data.get('result_url') or data.get('outputs', [None])[0]
                    elif status == 'failed':
                        return None
                
                time.sleep(interval)
            except Exception as e:
                time.sleep(interval)
        
        return None
        
    except Exception as e:
        log(f"Polling error: {str(e)}", level='ERROR')
        return None

def download_and_upload_image(task_id, image_url, filename):
    """Download image from URL and upload to ClickUp"""
    try:
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        image_bytes = img_response.content
        
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/attachment"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN
        }
        
        files = {
            'attachment': (filename, image_bytes, 'image/png')
        }
        
        response = requests.post(url, headers=headers, files=files, timeout=30)
        response.raise_for_status()
        
        log(f"✅ Uploaded: {filename}")
        return True
        
    except Exception as e:
        log(f"Error uploading {filename}: {e}", "ERROR")
        return False

def upload_temp_image(image_bytes):
    """Upload image to temporary storage and return URL"""
    # For now, we'll use the ClickUp attachment URL directly
    # In production, you'd upload to S3/CloudFlare R2/etc
    return None

def process_single_model_aspect(task_id, model, aspect_name, width, height, image_url, prompt):
    """Process a single model + aspect ratio combination"""
    try:
        model_name = model['name']
        endpoint = model['endpoint']
        display_name = model['display_name']
        
        log(f"Processing {display_name} - {aspect_name} ({width}x{height})")
        
        # Create job
        job_id, get_url = create_image_edit_job(
            image_url=image_url,
            prompt=prompt,
            width=width,
            height=height,
            endpoint=endpoint,
            model_name=model_name
        )
        
        if not job_id:
            log(f"⚠️ Failed to create job for {display_name}", level='WARNING')
            return None
        
        log(f"Job created: {job_id}")
        
        # Poll for result
        result_url = poll_for_result(job_id, endpoint, get_url)
        
        if not result_url:
            log(f"⚠️ {display_name} did not complete", level='WARNING')
            return None
        
        log(f"✅ {display_name} completed")
        
        # Upload to ClickUp
        filename = f"edited_{model_name}_{aspect_name.lower().replace(':', 'x')}.png"
        success = download_and_upload_image(task_id, result_url, filename)
        
        return filename if success else None
        
    except Exception as e:
        log(f"Error processing {model['name']}: {e}", "ERROR")
        return None

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
    Main Celery task - processes with 6 AI models in parallel
    """
    try:
        log(f"🚀 Starting task {task_id} (Worker: {self.request.hostname})")
        
        # Define all 6 models
        MODELS = [
            {
                'name': 'seedream',
                'endpoint': 'https://api.wavespeed.ai/api/v3/bytedance/seedream-v4/edit',
                'display_name': 'SeaDream v4'
            },
            {
                'name': 'qwen',
                'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit',
                'display_name': 'Qwen Edit'
            },
            {
                'name': 'qwenplus',
                'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit-plus',
                'display_name': 'Qwen Edit Plus'
            },
            {
                'name': 'wan25',
                'endpoint': 'https://api.wavespeed.ai/api/v3/alibaba/wan-2.5/image-edit',
                'display_name': 'Alibaba Wan 2.5'
            },
            {
                'name': 'qwenlora',
                'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit-lora',
                'display_name': 'Qwen LoRA'
            },
            {
                'name': 'nanobanana',
                'endpoint': 'https://api.wavespeed.ai/api/v3/google/nano-banana/edit',
                'display_name': 'Google Nano Banana'
            }
        ]
        
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
        
        # Convert to PNG
        log("Converting file to PNG...")
        image_bytes = convert_to_png(file_bytes, filename)
        if not image_bytes:
            return {"status": "error", "reason": "conversion_failed"}
        
        # Use the original ClickUp URL (all models accept URLs)
        image_url = file_url
        
        # Format prompt with Gemini
        log("Optimizing prompt with Gemini...")
        formatted_prompt = format_prompt_with_gemini(user_description)
        
        # Define aspect ratios
        aspect_ratios = {
            '9:16': (1088, 1920),
            '1:1': (1408, 1408)
        }
        
        log(f"📐 Processing {len(aspect_ratios)} aspect ratios × {len(MODELS)} models = {len(aspect_ratios) * len(MODELS)} total images")
        
        # Process all models in parallel
        uploaded_files = []
        
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = []
            for aspect_name, (width, height) in aspect_ratios.items():
                for model in MODELS:
                    future = executor.submit(
                        process_single_model_aspect,
                        task_id, model, aspect_name, width, height,
                        image_url, formatted_prompt
                    )
                    futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    uploaded_files.append(result)
        
        log(f"📊 Successfully uploaded {len(uploaded_files)}/{len(MODELS) * len(aspect_ratios)} images")
        
        # Uncheck field after ALL uploads
        update_custom_field(task_id, checked=False)
        
        log("✅ Task completed successfully!", "SUCCESS")
        
        # 🔓 Release lock on success
        try:
            redis_client = redis.from_url(config.REDIS_URL)
            redis_client.delete(f"task_lock:{task_id}")
            log(f"🔓 Lock released for task {task_id}")
        except Exception as lock_error:
            log(f"Warning: Could not release lock: {lock_error}", "WARNING")
        
        return {"status": "success", "task_id": task_id, "images_created": len(uploaded_files)}
        
    except Exception as e:
        log(f"Task failed: {e}", "ERROR")
        
        # 🔓 Release lock on failure too
        try:
            redis_client = redis.from_url(config.REDIS_URL)
            redis_client.delete(f"task_lock:{task_id}")
            log(f"🔓 Lock released for task {task_id} (after failure)")
        except Exception as lock_error:
            log(f"Warning: Could not release lock: {lock_error}", "WARNING")
        
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))