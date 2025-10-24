"""
Celery Tasks for ClickUp Image Processing
Using Proxy Server for URL-based validation (no more base64!)
"""
from celery_config import celery
from file_converters import convert_to_png
import requests
import time
import logging
import redis
from config import config
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import glob
import json
import hashlib
from datetime import datetime, timedelta
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================================
# PROXY SERVER MANAGEMENT
# ===============================================

from proxy_storage import create_proxy_url, get_proxy_token_data, get_proxy_stats

# ===============================================
# MAIN TASK FUNCTIONS
# ===============================================

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
        log(f"📡 Fetching task details for: {task_id}")
        response = requests.get(url, headers=get_clickup_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"❌ Error getting task details: {e}", "ERROR")
        return None

def get_task_attachments(task_id):
    """Get attachments from a ClickUp task"""
    try:
        task_data = get_task_details(task_id)
        if not task_data:
            return []
        attachments = task_data.get('attachments', [])
        log(f"📎 Found {len(attachments)} attachments")
        return attachments
    except Exception as e:
        log(f"❌ Error getting attachments: {e}", "ERROR")
        return []

def download_file(file_url):
    """Download file from URL with auth if needed"""
    try:
        headers = {}
        # Add auth for ClickUp URLs
        if 'clickup' in file_url.lower() or 'attachments' in file_url:
            headers = {"Authorization": config.CLICKUP_API_TOKEN}
        
        response = requests.get(file_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        log(f"❌ Download error: {e}", "ERROR")
        return None

def validate_image_with_claude(original_url, generated_url, user_description, prompt_used, model_name):
    """Simple validation with compressed base64 images"""
    try:
        from PIL import Image
        import base64
        
        log(f"🔍 Validating {model_name} output...")
        
        def download_compress_encode(url):
            """Download, compress, encode"""
            headers = {}
            if 'clickup' in url.lower():
                headers = {"Authorization": config.CLICKUP_API_TOKEN}
            
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                return None
            
            # Load and resize image
            img = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = bg
            
            # Resize if too big
            if max(img.size) > 800:
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            # Compress to JPEG
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            output.seek(0)
            
            # Encode to base64
            b64 = base64.b64encode(output.read()).decode('utf-8')
            return f"data:image/jpeg;base64,{b64}"
        
        original_data = download_compress_encode(original_url)
        generated_data = download_compress_encode(generated_url)
        
        if not original_data or not generated_data:
            return None
        
        log(f"✅ Images compressed and ready")
        
        # Call Claude via OpenRouter
        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"""Compare these images. User wanted: {user_description}
                    
Return ONLY this JSON (no other text):
{{"edit_accuracy_score": 0-100, "quality_score": 0-100, "text_score": 0-100, "overall_score": 0-100, "pass": true/false, "reasoning": "...", "suggested_prompt_refinement": "..."}}"""},
                    {"type": "image_url", "image_url": {"url": original_data}},
                    {"type": "image_url", "image_url": {"url": generated_data}}
                ]
            }],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            log(f"❌ API error: {response.status_code}", "ERROR")
            return None
        
        result = response.json()
        text = result['choices'][0]['message']['content'].strip()
        text = text.replace('```json', '').replace('```', '').strip()
        
        validation_result = json.loads(text)
        score = validation_result.get('overall_score', 0)
        
        log(f"📊 Score: {score}/100 - {'PASS' if score >= 90 else 'FAIL'}")
        
        return validation_result
        
    except Exception as e:
        log(f"❌ Validation error: {e}", "ERROR")
        return None

def generate_model_prompt(user_description, model_name):
    """Generate model-specific prompt using deep research + activation prompt"""
    try:
        log(f"🧠 Generating prompt for {model_name}")
        
        # Load BOTH research and activation files
        research_content = ""
        activation_content = ""
        research_dir = 'researches'
        
        if os.path.exists(research_dir):
            model_keywords = {
                'seedream': ['seedream'],
                'qwen': ['qwen'],
                'qwenplus': ['qwen'],  # Uses qwen research
                'wan25': ['wan2.5', 'wan25', 'wan'],
                'nanobanana': ['nano_banana', 'nanobanana', 'nano']
            }
            
            keywords = model_keywords.get(model_name, [model_name])
            
            # Load research file
            for keyword in keywords:
                pattern = os.path.join(research_dir, f"*{keyword}*_research.txt")
                files = glob.glob(pattern)
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        research_content = f.read()
                        log(f"📚 Loaded {len(research_content)} chars of research for {model_name}")
                        break
            
            # Load activation prompt file
            for keyword in keywords:
                pattern = os.path.join(research_dir, f"*{keyword}*_activation.txt")
                files = glob.glob(pattern)
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        activation_content = f.read()
                        log(f"🎯 Loaded {len(activation_content)} chars of activation prompt for {model_name}")
                        break
        
        # If we have an activation file, use it; otherwise use default
        if activation_content:
            # Use the pre-written activation prompt and insert research
            system_prompt = activation_content.replace('{RESEARCH}', research_content)
            log(f"✅ Using custom activation prompt for {model_name}")
        else:
            # Fallback to generic prompt if no activation file
            system_prompt = f"""You are a prompt optimizer for the {model_name} image editing model.

RESEARCH ABOUT {model_name.upper()}:
{research_content if research_content else "No specific research available for this model."}

YOUR TASK:
1. READ the user's editing request carefully
2. PRESERVE their exact intent - don't add creative interpretations
3. USE the research above to optimize the phrasing for {model_name}'s specific capabilities
4. Output ONLY the optimized prompt - no explanations, no markdown, no quotes

CRITICAL RULES:
- If user says "keep everything else the same" → emphasize this strongly
- Don't add background changes, don't add text that wasn't requested
- Preserve numerical values exactly
- Keep all Greek text exactly as provided"""
            log(f"⚠️ Using default activation prompt (no custom file found)")
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": config.YOUR_SITE_URL,
            "X-Title": "ClickUp Prompt Generator"
        }
        
        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""USER'S EDITING REQUEST:
{user_description}

Optimize this for {model_name} while preserving the EXACT intent. Output only the optimized prompt:"""}
            ],
            "temperature": 0.1,
            "max_tokens": 300
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        prompt = result['choices'][0]['message']['content'].strip()
        
        # Clean up the prompt
        prompt = prompt.replace('**', '').replace('"', '').replace('`', '').strip()
        
        log(f"✅ Generated prompt ({len(prompt)} chars): {prompt[:100]}...")
        return prompt
        
    except Exception as e:
        log(f"❌ Prompt generation error: {e}", "ERROR")
        return user_description

def refine_prompt_with_claude(original_prompt, validation_feedback, user_description, model_name):
    """Refine prompt based on validation feedback using full research + activation"""
    try:
        log(f"🔄 Refining prompt for {model_name}")
        log(f"📝 Original prompt was: {original_prompt}")
        log(f"💭 Claude's validation feedback: {validation_feedback}")
        
        # Load BOTH research and activation files
        research_content = ""
        activation_content = ""
        research_dir = 'researches'
        
        if os.path.exists(research_dir):
            model_keywords = {
                'seedream': ['seedream'],
                'qwen': ['qwen'],
                'qwenplus': ['qwen'],
                'wan25': ['wan2.5', 'wan25', 'wan'],
                'nanobanana': ['nano_banana', 'nanobanana', 'nano']
            }
            
            keywords = model_keywords.get(model_name, [model_name])
            
            # Load research
            for keyword in keywords:
                pattern = os.path.join(research_dir, f"*{keyword}*_research.txt")
                files = glob.glob(pattern)
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        research_content = f.read()
                        break
            
            # Load activation
            for keyword in keywords:
                pattern = os.path.join(research_dir, f"*{keyword}*_activation.txt")
                files = glob.glob(pattern)
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        activation_content = f.read()
                        break
        
        # Build refinement prompt
        if activation_content:
            # Use custom activation with refinement context
            refinement_context = f"""
REFINEMENT CONTEXT:
- Original prompt that failed: {original_prompt}
- Validation feedback: {validation_feedback}
- User's actual request: {user_description}

Your task is to refine the prompt based on this feedback while following the guidelines below.
"""
            system_prompt = refinement_context + "\n\n" + activation_content.replace('{RESEARCH}', research_content)
        else:
            # Fallback refinement prompt
            system_prompt = f"""You are refining a failed image editing prompt for the {model_name} model.

RESEARCH ABOUT {model_name.upper()}:
{research_content if research_content else "No specific research available."}

WHAT HAPPENED:
- Original prompt: {original_prompt}
- Validation result: {validation_feedback}
- User's actual request: {user_description}

YOUR TASK: Create a refined prompt that fixes the issues. Output ONLY the refined prompt."""
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": config.YOUR_SITE_URL,
            "X-Title": "ClickUp Prompt Refiner"
        }
        
        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""Based on the validation failure, create a refined prompt that will work better.

Remember the user wanted: {user_description}

Output only the refined prompt:"""}
            ],
            "temperature": 0.1,
            "max_tokens": 300
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        refined_prompt = result['choices'][0]['message']['content'].strip()
        
        # Clean up
        refined_prompt = refined_prompt.replace('**', '').replace('"', '').replace('`', '').strip()
        
        log(f"✅ REFINED PROMPT: {refined_prompt}")
        log(f"🔄 Next attempt will use: {refined_prompt[:100]}...")
        return refined_prompt
        
    except Exception as e:
        log(f"❌ Refinement error: {e}", "ERROR")
        return f"{original_prompt}. Keep all other elements exactly as they appear in the original image."

def create_image_edit_job(image_url, prompt, width, height, endpoint, model_name):
    """Create Wavespeed job for image editing"""
    try:
        log(f"🎨 Creating {model_name} job: {width}x{height}")
        
        headers = {
            'Authorization': f'Bearer {config.WAVESPEED_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Model-specific payload formatting
        if 'seedream' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'size': f'{width}*{height}'
            }
        elif 'qwen-image/edit-plus' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'seed': -1,
                'size': f'{width}*{height}',
                'output_format': 'png'
            }
        elif 'wan-2.5' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'seed': -1,
                'size': f'{width}*{height}'
            }
        elif 'nano-banana' in endpoint:
            aspect = "1:1" if width == height else "9:16"
            payload = {
                'aspect_ratio': aspect,
                'images': [image_url],
                'prompt': prompt,
                'output_format': 'png'
            }
        else:
            # Default Qwen format
            payload = {
                'image': image_url,
                'prompt': prompt,
                'seed': -1,
                'output_format': 'png'
            }
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data:
            job_id = data['data'].get('id')
            get_url = data['data'].get('urls', {}).get('get')
            log(f"✅ Job created: {job_id}")
            return job_id, get_url
        
        log(f"⚠️ No job ID in response", "WARNING")
        return None, None
        
    except Exception as e:
        log(f"❌ Job creation error: {e}", "ERROR")
        return None, None

def poll_for_result(job_id, endpoint, get_url=None):
    """Poll Wavespeed for job completion"""
    try:
        headers = {'Authorization': f'Bearer {config.WAVESPEED_API_KEY}'}
        status_url = get_url or f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"
        
        log(f"⏳ Polling job {job_id}")
        
        for attempt in range(60):  # Max 2 minutes
            response = requests.get(status_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data:
                status = data['data'].get('status')
                if status == 'completed':
                    outputs = data['data'].get('outputs', [])
                    if outputs:
                        log(f"✅ Job completed")
                        return outputs[0]
                elif status == 'failed':
                    log(f"❌ Job failed", "ERROR")
                    return None
            
            time.sleep(2)
        
        log(f"⏰ Job timeout after 2 minutes", "WARNING")
        return None
        
    except Exception as e:
        log(f"❌ Polling error: {e}", "ERROR")
        return None

def download_and_upload_image(task_id, image_url, filename):
    """Download generated image and upload to ClickUp"""
    try:
        log(f"📥 Downloading and uploading: {filename}")
        
        # Download the generated image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        
        # Upload to ClickUp
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/attachment"
        headers = {"Authorization": config.CLICKUP_API_TOKEN}
        files = {'attachment': (filename, img_response.content, 'image/png')}
        
        response = requests.post(url, headers=headers, files=files, timeout=30)
        response.raise_for_status()
        
        log(f"✅ Uploaded to ClickUp: {filename}")
        return True
        
    except Exception as e:
        log(f"❌ Upload error: {e}", "ERROR")
        return False

def process_single_model_aspect_with_validation(
    task_id, model, aspect_name, width, height,
    original_image_url, image_url, user_description, initial_prompt
):
    """Process single model/aspect with validation and retry logic"""
    model_name = model['name']
    endpoint = model['endpoint']
    display_name = model['display_name']
    
    logger.info(f"🚀 Starting {display_name} - {aspect_name}")
    
    MAX_RETRIES = 2
    current_prompt = initial_prompt
    SCORE_THRESHOLD = 90  # ← ADD THIS CONSTANT
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            logger.info(f"🔄 Attempt {attempt + 1}/{MAX_RETRIES + 1} for {display_name} - {aspect_name}")
            
            # Create job
            job_id, get_url = create_image_edit_job(
                image_url, current_prompt, width, height, endpoint, model_name
            )
            
            if not job_id:
                logger.warning(f"⚠️ Failed to create job")
                continue
            
            # Poll for result
            result_url = poll_for_result(job_id, endpoint, get_url)
            
            if not result_url:
                logger.warning(f"⚠️ No result received")
                continue
            
            # Validate using proxy URLs
            validation_result = validate_image_with_claude(
                original_image_url, result_url,
                user_description, current_prompt, model_name
            )
            
            # Handle None validation (API failure)
            if validation_result is None:
                logger.warning(f"⚠️ Validation failed, skipping")
                continue
            
            score = validation_result.get('overall_score', 0)
            
            # Only accept if score meets threshold
            if score >= SCORE_THRESHOLD:  # ← CHANGED FROM 85 TO 90
                logger.info(f"✅ PASSED validation: {score:.1f}/100")
                timestamp = int(time.time())
                filename = f"edited_{model_name}_{aspect_name.replace(':', 'x')}_score{int(score)}_{timestamp}.png"
                
                if download_and_upload_image(task_id, result_url, filename):
                    return filename
                return None
            
            # Refine and retry
            if attempt < MAX_RETRIES:
                log(f"❌ Score {score:.1f}/100 - Below threshold ({SCORE_THRESHOLD})")
                
                # Get the suggested refinement from validation
                suggested_refinement = validation_result.get('suggested_prompt_refinement', '')
                
                if suggested_refinement:
                    log(f"💡 Claude suggests: {suggested_refinement}")
                
                # Refine the prompt using Claude's suggestion
                current_prompt = refine_prompt_with_claude(
                    current_prompt,
                    suggested_refinement,
                    user_description,
                    model_name
                )
                
                log(f"🔄 Next attempt will use: {current_prompt[:100]}...")
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Processing error: {e}")
            if attempt == MAX_RETRIES:
                break
    
    logger.warning(f"❌ Failed all attempts for {display_name} - {aspect_name}")
    return None

def update_custom_field(task_id, checked=False):
    """Update the custom checkbox field in ClickUp"""
    try:
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/field/{config.CLICKUP_CUSTOM_FIELD_ID}"
        response = requests.post(
            url, 
            headers=get_clickup_headers(), 
            json={"value": checked}, 
            timeout=30
        )
        response.raise_for_status()
        log(f"✅ Checkbox updated: {'checked' if checked else 'unchecked'}")
        return True
    except Exception as e:
        log(f"⚠️ Could not update checkbox: {e}", "WARNING")
        return False

@celery.task(bind=True, max_retries=3)
def process_clickup_task(self, task_id, user_description):
    """Main Celery task for processing ClickUp image editing"""
    try:
        log(f"🚀 ========= STARTING TASK {task_id} =========")
        log(f"📝 Description: {user_description[:100]}...")
        
        start_time = time.time()
        
        # Model configurations
        MODELS = [
            {
                'name': 'seedream',
                'endpoint': 'https://api.wavespeed.ai/api/v3/bytedance/seedream-v4/edit',
                'display_name': 'SeaDream'
            },
            {
                'name': 'qwen',
                'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit',
                'display_name': 'Qwen'
            },
            {
                'name': 'qwenplus',
                'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit-plus',
                'display_name': 'Qwen+'
            },
            {
                'name': 'wan25',
                'endpoint': 'https://api.wavespeed.ai/api/v3/alibaba/wan-2.5/image-edit',
                'display_name': 'Wan2.5'
            },
            {
                'name': 'nanobanana',
                'endpoint': 'https://api.wavespeed.ai/api/v3/google/nano-banana/edit',
                'display_name': 'Nano'
            }
        ]
        
        # Get attachments
        attachments = get_task_attachments(task_id)
        if not attachments:
            log(f"❌ No attachments found", "ERROR")
            update_custom_field(task_id, checked=False)
            return {"status": "error", "reason": "no_attachments"}
        
        # Find the source image
        file_url = None
        filename = None
        for attachment in attachments:
            fname = attachment.get('title', '')
            # Skip already edited files
            if fname.startswith('edited_'):
                continue
            # Check for image files
            if any(fname.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.psd']):
                file_url = attachment.get('url')
                filename = fname
                log(f"📷 Found source image: {fname}")
                break
        
        if not file_url:
            log(f"❌ No valid image file found", "ERROR")
            update_custom_field(task_id, checked=False)
            return {"status": "error", "reason": "no_valid_file"}
        
        # Download and convert to PNG
        log(f"⬇️ Downloading source image...")
        file_bytes = download_file(file_url)
        if not file_bytes:
            log(f"❌ Could not download file", "ERROR")
            update_custom_field(task_id, checked=False)
            return {"status": "error", "reason": "download_failed"}
        
        log(f"🔄 Converting to PNG...")
        image_bytes = convert_to_png(file_bytes, filename)
        if not image_bytes:
            log(f"❌ Could not convert to PNG", "ERROR")
            update_custom_field(task_id, checked=False)
            return {"status": "error", "reason": "conversion_failed"}
        
        log(f"✅ Image ready for processing ({len(image_bytes) / 1024:.1f} KB)")
        
        # ========= PHASE 1: Generate prompts =========
        log(f"\n📝 === PHASE 1: PROMPT GENERATION ===")
        phase1_start = time.time()
        model_prompts = {}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_model = {
                executor.submit(generate_model_prompt, user_description, model['name']): model['name']
                for model in MODELS
            }
            
            for future in as_completed(future_to_model):
                model_name = future_to_model[future]
                try:
                    model_prompts[model_name] = future.result()
                except Exception as e:
                    log(f"⚠️ Prompt generation failed for {model_name}: {e}", "WARNING")
                    model_prompts[model_name] = user_description
        
        phase1_time = time.time() - phase1_start
        log(f"✅ Phase 1 complete: {len(model_prompts)} prompts in {phase1_time:.1f}s")
        
        # ========= PHASE 2 & 3: Generate and validate =========
        log(f"\n🎨 === PHASE 2 & 3: IMAGE GENERATION & VALIDATION ===")
        phase2_start = time.time()
        
        aspect_ratios = {
            '9:16': (1088, 1920),  # Portrait
            '1:1': (1408, 1408)     # Square
        }
        
        uploaded_files = []
        failed_attempts = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            # Queue all combinations
            for aspect_name, (width, height) in aspect_ratios.items():
                for model in MODELS:
                    model_prompt = model_prompts.get(model['name'], user_description)
                    
                    future = executor.submit(
                        process_single_model_aspect_with_validation,
                        task_id, model, aspect_name, width, height,
                        file_url, file_url, user_description, model_prompt
                    )
                    futures.append({
                        'future': future,
                        'model': model['display_name'],
                        'aspect': aspect_name
                    })
            
            # Collect results
            for item in futures:
                try:
                    result = item['future'].result(timeout=300)
                    if result:
                        uploaded_files.append(result)
                        log(f"✅ Success: {item['model']} - {item['aspect']}")
                    else:
                        failed_attempts.append(f"{item['model']} - {item['aspect']}")
                        log(f"⚠️ No valid image: {item['model']} - {item['aspect']}")
                except Exception as e:
                    failed_attempts.append(f"{item['model']} - {item['aspect']}")
                    log(f"❌ Failed: {item['model']} - {item['aspect']}: {e}", "ERROR")
        
        phase2_time = time.time() - phase2_start
        log(f"✅ Phase 2&3 complete: {len(uploaded_files)} images in {phase2_time:.1f}s")
        
        # ========= CLEANUP =========
        log(f"\n🧹 === CLEANUP ===")
        
        # Update checkbox to unchecked
        update_custom_field(task_id, checked=False)
        
        # Clear Redis lock
        try:
            redis_client = redis.from_url(config.REDIS_URL)
            redis_client.delete(f"task_lock:{task_id}")
            log(f"✅ Redis lock cleared")
        except Exception as e:
            log(f"⚠️ Could not clear Redis lock: {e}", "WARNING")
        
        # ========= FINAL REPORT =========
        total_time = time.time() - start_time
        log(f"\n✅ ========= TASK COMPLETE =========")
        log(f"📊 Results:")
        log(f"   • Images uploaded: {len(uploaded_files)}/10")
        log(f"   • Failed attempts: {len(failed_attempts)}")
        log(f"   • Total time: {total_time:.1f}s")
        log(f"   • Phase 1 (prompts): {phase1_time:.1f}s")
        log(f"   • Phase 2&3 (generate+validate): {phase2_time:.1f}s")
        
        if failed_attempts:
            log(f"❌ Failed: {', '.join(failed_attempts)}")
        
        return {
            "status": "success",
            "task_id": task_id,
            "images_created": len(uploaded_files),
            "uploaded_files": uploaded_files,
            "failed_attempts": failed_attempts,
            "total_time": total_time
        }
        
    except Exception as e:
        log(f"❌ TASK FAILED: {e}", "ERROR")
        update_custom_field(task_id, checked=False)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
