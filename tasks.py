"""
Celery Tasks for ClickUp Image Processing
Handles async background processing with 5 AI models
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
import glob

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

def format_prompt_with_claude(user_description, model_name):
    """
    Format user description into optimized prompt using Claude Sonnet 4.5
    Loads model-specific research and activation files dynamically
    """
    try:
        research_dir = 'researches'
        
        # Search for model-specific files (case-insensitive, partial match)
        def find_model_file(pattern_keywords, file_type):
            """Find file matching model name keywords"""
            if not os.path.exists(research_dir):
                log(f"⚠️ Research directory not found: {research_dir}", "WARNING")
                return ""
            
            # Try each keyword (e.g., 'qwen', 'nano', 'seedream')
            for keyword in pattern_keywords:
                # Search for files containing keyword
                search_pattern = os.path.join(research_dir, f"*{keyword}*{file_type}.txt")
                matching_files = glob.glob(search_pattern, recursive=False)
                
                if matching_files:
                    # Return first match
                    filepath = matching_files[0]
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            log(f"📄 Loaded: {os.path.basename(filepath)}")
                            return content
                    except Exception as e:
                        log(f"⚠️ Error reading {filepath}: {e}", "WARNING")
            
            return ""
        
        # Build search keywords based on model name
        # Handle special cases: qwen/qwenplus both use 'qwen', wan25 uses 'wan'
        search_keywords = []
        model_lower = model_name.lower()
        
        if 'qwen' in model_lower:
            search_keywords = ['qwen']
        elif 'wan' in model_lower:
            search_keywords = ['wan2.5', 'wan25', 'wan']
        elif 'nano' in model_lower or 'banana' in model_lower:
            search_keywords = ['nano_banana', 'nanobanana', 'nano']
        elif 'seedream' in model_lower:
            search_keywords = ['seedream']
        else:
            # Fallback: use model name as-is
            search_keywords = [model_name]
        
        # Load model-specific files
        activation_content = find_model_file(search_keywords, '_activation')
        research_content = find_model_file(search_keywords, '_research')
        
        # Fallback to generic files if model-specific not found
        if not activation_content:
            log(f"⚠️ No activation file found for {model_name}, using generic", "WARNING")
            try:
                with open('activation_guide.txt', 'r', encoding='utf-8') as f:
                    activation_content = f.read()
            except:
                activation_content = ""
        
        if not research_content:
            log(f"⚠️ No research file found for {model_name}, using generic", "WARNING")
            try:
                with open('deep_research.txt', 'r', encoding='utf-8') as f:
                    research_content = f.read()
            except:
                research_content = ""
        
        # Build system prompt
        system_prompt = f"""{activation_content}

{research_content}"""
        
        user_message = f"""USER DESCRIPTION: {user_description}

Think deeply about this vision and translate it into the perfect prompt for {model_name}.

OUTPUT (optimized prompt only):"""

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
        
        log(f"🧠 Sending to Claude for {model_name}...")
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        formatted_prompt = result['choices'][0]['message']['content'].strip()
        
        log(f"✅ Claude prompt ready for {model_name}: {formatted_prompt[:80]}...")
        return formatted_prompt
        
    except Exception as e:
        log(f"Error with Claude for {model_name}: {e}", "ERROR")
        return user_description

def create_image_edit_job(image_url, prompt, width, height, endpoint, model_name):
    """Create image editing job - supports all 5 models with correct payloads"""
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

def process_single_model_aspect(task_id, model, aspect_name, width, height, image_url, prompt):
    """Process a single model + aspect ratio combination with pre-generated prompt"""
    try:
        model_name = model['name']
        endpoint = model['endpoint']
        display_name = model['display_name']
        
        log(f"Processing {display_name} - {aspect_name} ({width}x{height})")
        
        # Create job with provided prompt
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
    Main Celery task - processes with 5 AI models in parallel
    Phase 1: Generate 5 model-specific prompts (parallel)
    Phase 2: Process 10 images (5 models × 2 aspects) (parallel)
    """
    try:
        log(f"🚀 Starting task {task_id} (Worker: {self.request.hostname})")
        
        # Define all 5 models
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
        
        log("PSD converted successfully")
        
        # Use the original ClickUp URL (all models accept URLs)
        image_url = file_url
        
        # PHASE 1: Generate model-specific prompts in parallel
        log("🧠 PHASE 1: Generating model-specific prompts with Claude Sonnet 4.5...")
        
        model_prompts = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_model = {
                executor.submit(format_prompt_with_claude, user_description, model['name']): model['name']
                for model in MODELS
            }
            
            for future in as_completed(future_to_model):
                model_name = future_to_model[future]
                try:
                    prompt = future.result()
                    model_prompts[model_name] = prompt
                except Exception as e:
                    log(f"⚠️ Failed to generate prompt for {model_name}: {e}", "WARNING")
                    model_prompts[model_name] = user_description  # Fallback to original
        
        log(f"✅ Generated {len(model_prompts)}/5 model-specific prompts")
        
        # Define aspect ratios
        aspect_ratios = {
            '9:16': (1088, 1920),
            '1:1': (1408, 1408)
        }
        
        # PHASE 2: Process all images in parallel
        log(f"🎨 PHASE 2: Processing {len(aspect_ratios)} aspect ratios × {len(MODELS)} models = {len(aspect_ratios) * len(MODELS)} total images")
        
        uploaded_files = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for aspect_name, (width, height) in aspect_ratios.items():
                for model in MODELS:
                    # Get pre-generated prompt for this model
                    model_prompt = model_prompts.get(model['name'], user_description)
                    
                    future = executor.submit(
                        process_single_model_aspect,
                        task_id, model, aspect_name, width, height,
                        image_url, model_prompt
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