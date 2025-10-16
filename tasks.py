"""
Celery Tasks for ClickUp Image Processing
Handles async background processing with 5 AI models + AI Validation
WITH COMPREHENSIVE LOGGING
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
import json

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
        log(f"📡 Fetching task details for: {task_id}")
        response = requests.get(url, headers=get_clickup_headers())
        response.raise_for_status()
        log(f"✅ Task details retrieved successfully")
        return response.json()
    except Exception as e:
        log(f"❌ Error getting task details: {e}", "ERROR")
        return None

def get_task_attachments(task_id):
    """Get attachments from a ClickUp task"""
    try:
        log(f"📎 Getting attachments for task: {task_id}")
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
    """Download file from URL and return as bytes"""
    try:
        log(f"⬇️ Downloading file from: {file_url[:50]}...")
        start_time = time.time()
        response = requests.get(file_url)
        response.raise_for_status()
        elapsed = time.time() - start_time
        size_mb = len(response.content) / (1024 * 1024)
        log(f"✅ File downloaded: {size_mb:.2f} MB in {elapsed:.2f}s")
        return response.content
    except Exception as e:
        log(f"❌ Error downloading file: {e}", "ERROR")
        return None

def add_validation_comment_to_clickup(task_id, model_name, aspect_name, validation_result):
    """Add validation report as comment to ClickUp task"""
    try:
        log(f"💬 Adding validation comment for {model_name} - {aspect_name}")
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/comment"
        
        # Build comment text
        pass_emoji = "✅" if validation_result['pass'] else "⚠️"
        status = "PASSED" if validation_result['pass'] else "NEEDS MANUAL REVIEW"
        
        comment_text = f"""
{pass_emoji} **Validation Report: {model_name} - {aspect_name}**

**Overall Score:** {validation_result['overall_score']:.1f}/100 - {status}

**Detailed Scores:**
- Greek Text Quality: {validation_result['greek_text_score']}/100
- Prompt Adherence: {validation_result['prompt_adherence_score']}/100
- Visual Quality: {validation_result['visual_quality_score']}/100

**Analysis:**
{validation_result['reasoning']}

**Attempt:** {validation_result.get('attempt', 1)}/3
        """.strip()
        
        payload = {
            "comment_text": comment_text
        }
        
        log(f"📝 Comment content:\n{comment_text}")
        
        response = requests.post(url, headers=get_clickup_headers(), json=payload)
        response.raise_for_status()
        
        log(f"✅ Validation comment added successfully")
        return True
        
    except Exception as e:
        log(f"❌ Error adding validation comment: {e}", "ERROR")
        return False

def validate_image_with_claude(original_image_url, generated_image_url, user_description, model_prompt, model_name):
    """
    Validate generated image using Claude Sonnet 4.5
    Compares generated image against original + user request
    
    Returns validation result dict with scores and feedback
    """
    try:
        log(f"=" * 80)
        log(f"🔍 STARTING VALIDATION for {model_name}")
        log(f"=" * 80)
        log(f"📸 Original Image: {original_image_url[:60]}...")
        log(f"🎨 Generated Image: {generated_image_url[:60]}...")
        log(f"📝 User Description: {user_description}")
        log(f"🧠 Model Prompt Used: {model_prompt[:150]}...")
        
        # Build validation prompt
        validation_prompt = f"""You are an expert image quality validator for AI-generated marketing materials.

**USER'S ORIGINAL REQUEST:**
{user_description}

**MODEL-SPECIFIC PROMPT USED:**
{model_prompt}

**TASK:**
You will receive TWO images:
1. ORIGINAL IMAGE (the source material)
2. GENERATED IMAGE (the AI-edited result)

Compare them carefully and validate:

**1. Greek Text Validation (0-100):**
- Are Greek characters correct and readable? (no garbled text like Γ†Π°Π·Π΄)
- Is text properly formed and legible?
- Does Greek text quality match the original's text quality?
Score: ___/100

**2. Prompt Adherence (0-100):**
- Did it follow the user's original request accurately?
- Are the requested changes present in the generated image?
- Does it match what the user asked for (not just what the model prompt said)?
- Are elements preserved that should stay the same (logo, fonts, layout)?
Score: ___/100

**3. Visual Quality (0-100):**
- No artifacts, distortions, or hallucinations?
- Professional appearance maintained?
- Logo and brand elements preserved correctly?
- Font styles consistent with original (unless change was requested)?
- Colors and composition appropriate?
Score: ___/100

**4. OVERALL SCORE:** (average of above three scores)

**5. PASS/FAIL:** 
- PASS if overall >= 90
- FAIL if overall < 90

**6. REASONING:** (2-3 sentences explaining the scores, focusing on specific observed issues or successes)

**7. IF FAIL - Suggested Prompt Refinement:**
(If score < 90, provide specific suggestions on how to improve the prompt for better results. Be concrete and actionable.)

**CRITICAL:** 
- Don't be overly strict - minor imperfections are acceptable (one extra period is OK)
- Focus on major issues: garbled text, missing requested changes, broken logos, significant hallucinations
- A score of 85-90 should only fail if there are clear problems
- Greek text should be legible but doesn't need to be perfect

**OUTPUT FORMAT (JSON only, no other text):**
{{
  "greek_text_score": 95,
  "prompt_adherence_score": 88,
  "visual_quality_score": 92,
  "overall_score": 91.67,
  "pass": true,
  "reasoning": "The generated image successfully implements the requested changes. Greek text is clear and legible with proper character formation. Minor artifacts in the background but overall professional quality maintained.",
  "suggested_prompt_refinement": "To improve further, specify exact positioning for the logo and ensure shadows match the lighting direction."
}}
"""

        log(f"📤 Sending validation request to Claude Sonnet 4.5...")
        log(f"🔧 Using model: {config.OPENROUTER_MODEL}")
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://clickup-ai-workflow.app",
            "X-Title": "ClickUp AI Image Validator"
        }
        
        # Build message with both images
        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": validation_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": original_image_url
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": generated_image_url
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.4,  # Lower temperature for consistent validation
            "max_tokens": 1000
        }
        
        start_time = time.time()
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        elapsed = time.time() - start_time
        
        log(f"⏱️ Claude validation took {elapsed:.2f}s")
        
        result = response.json()
        validation_text = result['choices'][0]['message']['content'].strip()
        
        log(f"📥 Raw Claude Response:")
        log(f"{validation_text}")
        
        # Parse JSON from response (handle markdown code blocks if present)
        validation_text = validation_text.replace('```json', '').replace('```', '').strip()
        validation_result = json.loads(validation_text)
        
        log(f"=" * 80)
        log(f"📊 VALIDATION RESULTS for {model_name}:")
        log(f"=" * 80)
        log(f"🇬🇷 Greek Text Score: {validation_result['greek_text_score']}/100")
        log(f"🎯 Prompt Adherence Score: {validation_result['prompt_adherence_score']}/100")
        log(f"✨ Visual Quality Score: {validation_result['visual_quality_score']}/100")
        log(f"📈 OVERALL SCORE: {validation_result['overall_score']:.1f}/100")
        log(f"{'✅ PASS' if validation_result['pass'] else '❌ FAIL'}")
        log(f"💭 Reasoning: {validation_result['reasoning']}")
        if not validation_result['pass']:
            log(f"🔧 Suggested Refinement: {validation_result['suggested_prompt_refinement']}")
        log(f"=" * 80)
        
        return validation_result
        
    except json.JSONDecodeError as e:
        log(f"❌ JSON Parsing Error for {model_name}:", "ERROR")
        log(f"Raw response that failed to parse: {validation_text}", "ERROR")
        log(f"Error details: {e}", "ERROR")
        # Return safe fallback
        return {
            "greek_text_score": 80,
            "prompt_adherence_score": 80,
            "visual_quality_score": 80,
            "overall_score": 80,
            "pass": False,
            "reasoning": "Validation parsing error - defaulting to retry",
            "suggested_prompt_refinement": "Ensure all requested changes are clearly specified"
        }
    except Exception as e:
        log(f"❌ Validation API Error for {model_name}: {e}", "ERROR")
        # Return safe fallback
        return {
            "greek_text_score": 75,
            "prompt_adherence_score": 75,
            "visual_quality_score": 75,
            "overall_score": 75,
            "pass": False,
            "reasoning": "Validation API error - defaulting to retry",
            "suggested_prompt_refinement": "Review and strengthen prompt specificity"
        }

def refine_prompt_with_claude(original_prompt, validation_feedback, user_description, model_name):
    """
    Refine prompt based on validation feedback
    Re-uses deep research files + incorporates validation suggestions
    """
    try:
        log(f"=" * 80)
        log(f"🔧 REFINING PROMPT for {model_name}")
        log(f"=" * 80)
        log(f"📝 Original Prompt: {original_prompt}")
        log(f"💡 Validation Feedback: {validation_feedback}")
        
        research_dir = 'researches'
        
        # Load model-specific research files (same logic as format_prompt_with_claude)
        def find_model_file(pattern_keywords, file_type):
            if not os.path.exists(research_dir):
                log(f"⚠️ Research directory not found: {research_dir}", "WARNING")
                return ""
            
            for keyword in pattern_keywords:
                search_pattern = os.path.join(research_dir, f"*{keyword}*{file_type}.txt")
                matching_files = glob.glob(search_pattern, recursive=False)
                
                if matching_files:
                    filepath = matching_files[0]
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            log(f"📄 Loaded research file: {os.path.basename(filepath)}")
                            return content
                    except Exception as e:
                        log(f"⚠️ Error reading {filepath}: {e}", "WARNING")
            
            return ""
        
        # Build search keywords based on model name
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
            search_keywords = [model_name]
        
        log(f"🔍 Searching for research files with keywords: {search_keywords}")
        
        # Load model-specific files
        activation_content = find_model_file(search_keywords, '_activation')
        research_content = find_model_file(search_keywords, '_research')
        
        # Fallback to generic
        if not activation_content:
            log(f"⚠️ No model-specific activation found, using generic", "WARNING")
            try:
                with open('activation_guide.txt', 'r', encoding='utf-8') as f:
                    activation_content = f.read()
                    log(f"📄 Loaded generic activation_guide.txt")
            except:
                activation_content = ""
        
        if not research_content:
            log(f"⚠️ No model-specific research found, using generic", "WARNING")
            try:
                with open('deep_research.txt', 'r', encoding='utf-8') as f:
                    research_content = f.read()
                    log(f"📄 Loaded generic deep_research.txt")
            except:
                research_content = ""
        
        # Build refined system prompt
        system_prompt = f"""{activation_content}

{research_content}

IMPORTANT CONTEXT - VALIDATION FEEDBACK:
The previous prompt generated an image that scored below 90%. Here's what needs improvement:
{validation_feedback}

Use this feedback to refine the prompt and address the specific issues identified."""

        user_message = f"""ORIGINAL USER REQUEST: {user_description}

PREVIOUS PROMPT (that didn't pass validation): {original_prompt}

VALIDATION ISSUES: {validation_feedback}

**CRITICAL INSTRUCTIONS:**
1. Output ONLY a direct, executable image editing prompt
2. NO explanations, NO analysis, NO workflows, NO tutorials
3. NO phrases like "Based on", "The model's", "STAGE 1", etc.
4. JUST the editing instructions in plain language
5. Maximum 2-3 sentences

Example of what to output:
"Move the KUDU COFFEE logo 200 pixels to the right. Change the text '20%' to '30%' maintaining the same font weight and color."

Example of what NOT to output:
"Based on the validation feedback, the architectural reality suggests a multi-stage workflow..."

Create a REFINED, DIRECT prompt for {model_name} that addresses the validation issues.

OUTPUT (refined prompt only - NO OTHER TEXT):"""

        log(f"📤 Sending refinement request to Claude...")
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://clickup-ai-workflow.app",
            "X-Title": "ClickUp AI Prompt Refiner"
        }
        
        payload = {
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.5,
            "max_tokens": 1000,
            "top_p": 0.90
        }
        
        start_time = time.time()
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        elapsed = time.time() - start_time
        
        log(f"⏱️ Prompt refinement took {elapsed:.2f}s")
        
        result = response.json()
        refined_prompt = result['choices'][0]['message']['content'].strip()
        
        log(f"✅ REFINED PROMPT:")
        log(f"{refined_prompt}")
        log(f"=" * 80)
        
        return refined_prompt
        
    except Exception as e:
        log(f"❌ Error refining prompt for {model_name}: {e}", "ERROR")
        # Fallback to original with minor modification
        fallback = f"{original_prompt} (Enhanced: {validation_feedback})"
        log(f"⚠️ Using fallback refined prompt: {fallback}")
        return fallback

def format_prompt_with_claude(user_description, model_name):
    """
    Format user description into optimized prompt using Claude Sonnet 4.5
    Loads model-specific research and activation files dynamically
    """
    try:
        log(f"=" * 80)
        log(f"🧠 GENERATING PROMPT for {model_name}")
        log(f"=" * 80)
        log(f"📝 User Description: {user_description}")
        
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
        
        log(f"🔍 Searching for files with keywords: {search_keywords}")
        
        # Load model-specific files
        activation_content = find_model_file(search_keywords, '_activation')
        research_content = find_model_file(search_keywords, '_research')
        
        # Fallback to generic files if model-specific not found
        if not activation_content:
            log(f"⚠️ No activation file found for {model_name}, using generic", "WARNING")
            try:
                with open('activation_guide.txt', 'r', encoding='utf-8') as f:
                    activation_content = f.read()
                    log(f"📄 Loaded generic activation_guide.txt")
            except:
                activation_content = ""
                log(f"⚠️ No generic activation file found", "WARNING")
        
        if not research_content:
            log(f"⚠️ No research file found for {model_name}, using generic", "WARNING")
            try:
                with open('deep_research.txt', 'r', encoding='utf-8') as f:
                    research_content = f.read()
                    log(f"📄 Loaded generic deep_research.txt")
            except:
                research_content = ""
                log(f"⚠️ No generic research file found", "WARNING")
        
        # Build system prompt
        system_prompt = f"""You are a PROMPT GENERATOR, not a pattern navigator.

            Your ONLY job: Convert user descriptions into SHORT, DIRECT image editing prompts.

            {activation_content}

            {research_content}

            **CRITICAL - YOUR ROLE:**
            - The above research teaches you PATTERNS
            - YOU must OUTPUT a simple prompt using those patterns
            - DO NOT explain the patterns
            - DO NOT write tutorials or workflows
            - DO NOT use phrases like "Based on the patterns...", "Stage 1:", "Workflow:", etc.

            **YOU ARE NOT:** A pattern navigator, tutorial writer, or workflow designer
            **YOU ARE:** A prompt generator that uses patterns to create concise instructions"""
        
        log(f"📦 System prompt built (length: {len(system_prompt)} chars)")
        
        user_message = f"""USER DESCRIPTION: {user_description}

Think deeply about this vision and translate it into the perfect prompt for {model_name}.

OUTPUT (optimized prompt only):"""

        log(f"📤 Sending to Claude Sonnet 4.5...")
        log(f"🔧 Model: {config.OPENROUTER_MODEL}")
        
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
            "temperature": 0.5,
            "max_tokens": 1000,
            "top_p": 0.90,
            "stream": False
        }
        
        start_time = time.time()
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        elapsed = time.time() - start_time
        
        log(f"⏱️ Prompt generation took {elapsed:.2f}s")
        
        result = response.json()
        formatted_prompt = result['choices'][0]['message']['content'].strip()
        
        log(f"✅ GENERATED PROMPT for {model_name}:")
        log(f"{formatted_prompt}")
        log(f"=" * 80)
        
        return formatted_prompt
        
    except Exception as e:
        log(f"❌ Error with Claude for {model_name}: {e}", "ERROR")
        log(f"⚠️ Falling back to original user description", "WARNING")
        return user_description

def create_image_edit_job(image_url, prompt, width, height, endpoint, model_name):
    """Create image editing job - supports all 5 models with correct payloads"""
    try:
        log(f"🎨 Creating image edit job for {model_name}")
        log(f"📐 Dimensions: {width}x{height}")
        log(f"🔗 Endpoint: {endpoint}")
        log(f"📝 Prompt: {prompt[:100]}...")
        
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
            log(f"📦 Payload type: SeaDream")
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
            log(f"📦 Payload type: Qwen Edit Plus")
        elif 'wan-2.5' in endpoint:
            payload = {
                'images': [image_url],
                'prompt': prompt,
                'seed': -1,
                'size': f'{width}*{height}'
            }
            log(f"📦 Payload type: Alibaba Wan 2.5")
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
            log(f"📦 Payload type: Nano Banana (aspect: {aspect})")
        else:  # qwen-image/edit (base)
            payload = {
                'enable_base64_output': False,
                'enable_sync_mode': False,
                'image': image_url,
                'output_format': 'png',
                'prompt': prompt,
                'seed': -1
            }
            log(f"📦 Payload type: Qwen Edit")
        
        log(f"📤 Sending request to Wavespeed API...")
        start_time = time.time()
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        elapsed = time.time() - start_time
        log(f"⏱️ Job creation took {elapsed:.2f}s")
        
        # Extract job ID
        if 'data' in data:
            job_id = data['data'].get('id')
            get_url = data['data'].get('urls', {}).get('get')
            log(f"✅ Job created - ID: {job_id}")
            if get_url:
                log(f"🔗 Status URL: {get_url}")
            return job_id, get_url
        elif 'requestId' in data:
            job_id = data['requestId']
            log(f"✅ Job created - Request ID: {job_id}")
            return job_id, None
        
        log(f"⚠️ Unexpected response format: {data}", "WARNING")
        return None, None
        
    except Exception as e:
        log(f"❌ Error creating job for {model_name}: {str(e)}", level='ERROR')
        return None, None

def poll_for_result(job_id, endpoint, get_url=None, max_attempts=60, interval=2):
    """Poll for job result"""
    try:
        log(f"⏳ Polling for result - Job ID: {job_id}")
        log(f"📊 Max attempts: {max_attempts}, Interval: {interval}s")
        
        headers = {
            'Authorization': f'Bearer {config.WAVESPEED_API_KEY}'
        }
        
        # Build status URL
        if get_url:
            status_url = get_url
        else:
            status_url = f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"
        
        log(f"🔗 Polling URL: {status_url}")
        
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
                            result_url = outputs[0]
                            log(f"✅ Job completed! Result: {result_url[:60]}...")
                            return result_url
                    elif status == 'failed':
                        log(f"❌ Job failed", "ERROR")
                        return None
                    else:
                        if attempt % 10 == 0:  # Log every 10 attempts
                            log(f"⏳ Status: {status} (attempt {attempt + 1}/{max_attempts})")
                else:
                    status = data.get('status')
                    if status == 'completed' or status == 'succeeded':
                        result = data.get('output') or data.get('result_url') or data.get('outputs', [None])[0]
                        if result:
                            log(f"✅ Job completed! Result: {result[:60]}...")
                            return result
                    elif status == 'failed':
                        log(f"❌ Job failed", "ERROR")
                        return None
                    else:
                        if attempt % 10 == 0:
                            log(f"⏳ Status: {status} (attempt {attempt + 1}/{max_attempts})")
                
                time.sleep(interval)
            except Exception as e:
                if attempt % 10 == 0:
                    log(f"⚠️ Polling error (attempt {attempt + 1}): {e}", "WARNING")
                time.sleep(interval)
        
        log(f"⏱️ Timeout: Max polling attempts reached", "WARNING")
        return None
        
    except Exception as e:
        log(f"❌ Polling error: {str(e)}", level='ERROR')
        return None

def download_and_upload_image(task_id, image_url, filename):
    """Download image from URL and upload to ClickUp"""
    try:
        log(f"📥 Downloading image for upload: {filename}")
        log(f"🔗 Source: {image_url[:60]}...")
        
        start_time = time.time()
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        image_bytes = img_response.content
        
        download_time = time.time() - start_time
        size_mb = len(image_bytes) / (1024 * 1024)
        log(f"✅ Image downloaded: {size_mb:.2f} MB in {download_time:.2f}s")
        
        url = f"{config.CLICKUP_API_BASE}/task/{task_id}/attachment"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN
        }
        
        files = {
            'attachment': (filename, image_bytes, 'image/png')
        }
        
        log(f"📤 Uploading to ClickUp: {filename}")
        start_time = time.time()
        
        response = requests.post(url, headers=headers, files=files, timeout=30)
        response.raise_for_status()
        
        upload_time = time.time() - start_time
        log(f"✅ Uploaded successfully in {upload_time:.2f}s: {filename}")
        return True
        
    except Exception as e:
        log(f"❌ Error uploading {filename}: {e}", "ERROR")
        return False

def process_single_model_aspect_with_validation(
    task_id, model, aspect_name, width, height, 
    original_image_url, image_url, user_description, initial_prompt
):
    """
    Process a single model + aspect ratio with validation and retry logic
    Max 3 attempts (1 initial + 2 retries)
    """
    model_name = model['name']
    endpoint = model['endpoint']
    display_name = model['display_name']
    
    log(f"\n{'=' * 80}")
    log(f"🚀 STARTING: {display_name} - {aspect_name}")
    log(f"{'=' * 80}")
    
    MAX_RETRIES = 2  # Total 3 attempts
    best_result = None
    best_score = 0
    
    current_prompt = initial_prompt
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            attempt_num = attempt + 1
            log(f"\n{'─' * 80}")
            log(f"🔄 ATTEMPT {attempt_num}/3 for {display_name} - {aspect_name}")
            log(f"{'─' * 80}")
            log(f"📝 Current prompt: {current_prompt[:150]}...")
            
            # Create image editing job
            job_id, get_url = create_image_edit_job(
                image_url=image_url,
                prompt=current_prompt,
                width=width,
                height=height,
                endpoint=endpoint,
                model_name=model_name
            )
            
            if not job_id:
                log(f"⚠️ Failed to create job (attempt {attempt_num})", level='WARNING')
                if attempt < MAX_RETRIES:
                    log(f"🔄 Will retry...")
                    continue
                else:
                    log(f"❌ No more retries left", "ERROR")
                    break
            
            # Poll for result
            result_url = poll_for_result(job_id, endpoint, get_url)
            
            if not result_url:
                log(f"⚠️ Image generation failed (attempt {attempt_num})", level='WARNING')
                if attempt < MAX_RETRIES:
                    log(f"🔄 Will retry...")
                    continue
                else:
                    log(f"❌ No more retries left", "ERROR")
                    break
            
            # 🆕 PHASE 3: VALIDATE IMAGE
            log(f"\n{'─' * 40}")
            log(f"🔍 VALIDATION PHASE")
            log(f"{'─' * 40}")
            
            validation_result = validate_image_with_claude(
                original_image_url=original_image_url,
                generated_image_url=result_url,
                user_description=user_description,
                model_prompt=current_prompt,
                model_name=model_name
            )
            
            validation_result['attempt'] = attempt_num
            
            # Track best result
            if validation_result['overall_score'] > best_score:
                best_score = validation_result['overall_score']
                best_result = {
                    'result_url': result_url,
                    'validation': validation_result,
                    'prompt': current_prompt,
                    'attempt': attempt_num
                }
                log(f"📊 New best score: {best_score:.1f}/100")
            
            # Check if passed (>= 90%)
            if validation_result['overall_score'] >= 90:
                log(f"\n{'🎉' * 20}")
                log(f"✅ VALIDATION PASSED: {validation_result['overall_score']:.1f}/100")
                log(f"{'🎉' * 20}\n")
                
                # Generate filename with score and timestamp
                timestamp = int(time.time())
                score = int(validation_result['overall_score'])
                filename = f"{model_name}_{aspect_name.lower().replace(':', 'x')}_score{score}_{timestamp}.png"
                
                log(f"📝 Generated filename: {filename}")
                
                # Upload immediately
                success = download_and_upload_image(task_id, result_url, filename)
                
                if success:
                    # Add validation comment
                    add_validation_comment_to_clickup(
                        task_id, 
                        display_name, 
                        aspect_name, 
                        validation_result
                    )
                    log(f"✅ COMPLETE: {display_name} - {aspect_name}")
                    return filename
                else:
                    log(f"⚠️ Upload failed", "WARNING")
                    if attempt < MAX_RETRIES:
                        log(f"🔄 Will retry...")
                        continue
                    else:
                        log(f"❌ No more retries left", "ERROR")
                        break
            
            else:
                # Failed validation
                log(f"\n{'❌' * 20}")
                log(f"❌ VALIDATION FAILED: {validation_result['overall_score']:.1f}/100")
                log(f"{'❌' * 20}\n")
                
                if attempt < MAX_RETRIES:
                    # Retry with refined prompt
                    log(f"🔄 RETRY LOGIC ACTIVATED")
                    log(f"📊 Current score: {validation_result['overall_score']:.1f}/100 (need 90+)")
                    log(f"🎯 Attempts remaining: {MAX_RETRIES - attempt}")
                    
                    current_prompt = refine_prompt_with_claude(
                        original_prompt=current_prompt,
                        validation_feedback=validation_result['suggested_prompt_refinement'],
                        user_description=user_description,
                        model_name=model_name
                    )
                    
                    log(f"✅ Prompt refined, moving to next attempt...")
                    # Continue to next attempt
                    continue
                else:
                    # Max retries reached
                    log(f"\n{'⚠️' * 20}")
                    log(f"⚠️ MAX RETRIES REACHED")
                    log(f"📊 Best score achieved: {best_score:.1f}/100")
                    log(f"{'⚠️' * 20}\n")
                    break
        
        except Exception as e:
            log(f"❌ ERROR in attempt {attempt_num}: {e}", "ERROR")
            if attempt < MAX_RETRIES:
                log(f"🔄 Will retry...")
                continue
            else:
                log(f"❌ No more retries left", "ERROR")
                break
    
    # If we get here, either max retries reached or all attempts failed
    # Upload best result with warning
    if best_result:
        log(f"\n{'⚠️' * 20}")
        log(f"⚠️ UPLOADING WITH MANUAL REVIEW FLAG")
        log(f"📊 Best score: {best_result['validation']['overall_score']:.1f}/100")
        log(f"🔢 Achieved in attempt: {best_result['attempt']}/3")
        log(f"{'⚠️' * 20}\n")
        
        timestamp = int(time.time())
        score = int(best_result['validation']['overall_score'])
        filename = f"{model_name}_{aspect_name.lower().replace(':', 'x')}_score{score}_{timestamp}_REVIEW.png"
        
        log(f"📝 Filename with review flag: {filename}")
        
        success = download_and_upload_image(task_id, best_result['result_url'], filename)
        
        if success:
            # Add validation comment with warning
            best_result['validation']['reasoning'] = f"⚠️ NEEDS MANUAL REVIEW - Best score after {best_result['attempt']} attempts. {best_result['validation']['reasoning']}"
            
            add_validation_comment_to_clickup(
                task_id,
                display_name,
                aspect_name,
                best_result['validation']
            )
            log(f"✅ Uploaded with manual review flag: {filename}")
            return filename
        else:
            log(f"❌ Failed to upload best result", "ERROR")
    else:
        log(f"❌ No valid results to upload", "ERROR")
    
    log(f"❌ ALL ATTEMPTS FAILED: {display_name} - {aspect_name}")
    return None

def update_custom_field(task_id, checked=False):
    """Update boolean custom field"""
    try:
        log(f"🔧 Updating custom field checkbox: {'CHECKED' if checked else 'UNCHECKED'}")
        url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{config.CLICKUP_CUSTOM_FIELD_ID}"
        
        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json={"value": checked})
        response.raise_for_status()
        
        log(f"✅ Checkbox updated successfully")
        return True
        
    except Exception as e:
        log(f"❌ Error updating checkbox: {e}", "ERROR")
        return False

@celery.task(bind=True, max_retries=3)
def process_clickup_task(self, task_id, user_description):
    """
    Main Celery task - processes with 5 AI models + AI validation in parallel
    Phase 1: Generate 5 model-specific prompts (parallel)
    Phase 2: Generate 10 images (parallel)
    Phase 3: Validate 10 images (parallel, with retry logic per image)
    """
    try:
        log(f"\n{'#' * 80}")
        log(f"{'#' * 80}")
        log(f"🚀 TASK STARTED: {task_id}")
        log(f"👤 Worker: {self.request.hostname}")
        log(f"📝 User Description: {user_description}")
        log(f"{'#' * 80}")
        log(f"{'#' * 80}\n")
        
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
        
        log(f"🤖 Configured models: {len(MODELS)}")
        for model in MODELS:
            log(f"  • {model['display_name']} ({model['name']})")
        
        # Get attachments
        attachments = get_task_attachments(task_id)
        if not attachments:
            log("❌ No attachments found", "ERROR")
            return {"status": "error", "reason": "no_attachments"}
        
        # Find first supported file
        file_url = None
        filename = None
        for attachment in attachments:
            fname = attachment.get('title', '')
            
            log(f"📎 Checking attachment: {fname}")

            if fname.startswith('edited_'):
                log(f"  ⏭️ Skipping (already edited)")
                continue

            if any(fname.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.psd', '.gif', '.bmp']):
                file_url = attachment.get('url')
                filename = fname
                log(f"  ✅ Selected: {fname}")
                break
            else:
                log(f"  ⏭️ Skipping (unsupported format)")
        
        if not file_url:
            log("❌ No supported file found", "ERROR")
            return {"status": "error", "reason": "unsupported_format"}
        
        # Download file
        file_bytes = download_file(file_url)
        if not file_bytes:
            return {"status": "error", "reason": "download_failed"}
        
        # Convert to PNG if needed
        log(f"🔄 Converting {filename} to PNG...")
        image_bytes = convert_to_png(file_bytes, filename)
        if not image_bytes:
            log("❌ Conversion failed", "ERROR")
            return {"status": "error", "reason": "conversion_failed"}
        
        log(f"✅ Conversion successful")
        
        # Use the original ClickUp URL (all models accept URLs)
        image_url = file_url
        original_image_url = file_url  # Store for validation
        
        log(f"🔗 Image URL: {image_url[:60]}...")
        
        # PHASE 1: Generate model-specific prompts in parallel
        log(f"\n{'=' * 80}")
        log(f"🧠 PHASE 1: PROMPT GENERATION")
        log(f"{'=' * 80}")
        log(f"📊 Generating {len(MODELS)} model-specific prompts in parallel...")
        
        phase1_start = time.time()
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
                    log(f"✅ Prompt ready: {model_name}")
                except Exception as e:
                    log(f"❌ Failed to generate prompt for {model_name}: {e}", "WARNING")
                    model_prompts[model_name] = user_description  # Fallback to original
                    log(f"⚠️ Using fallback prompt for {model_name}")
        
        phase1_time = time.time() - phase1_start
        log(f"\n✅ PHASE 1 COMPLETE")
        log(f"📊 Generated: {len(model_prompts)}/{len(MODELS)} prompts")
        log(f"⏱️ Time: {phase1_time:.2f}s")
        log(f"{'=' * 80}\n")
        
        # Define aspect ratios
        aspect_ratios = {
            '9:16': (1088, 1920),
            '1:1': (1408, 1408)
        }
        
        total_images = len(aspect_ratios) * len(MODELS)
        
        # PHASE 2 + 3: Process all images with validation in parallel
        log(f"\n{'=' * 80}")
        log(f"🎨 PHASE 2+3: IMAGE GENERATION & VALIDATION")
        log(f"{'=' * 80}")
        log(f"📊 Processing {len(aspect_ratios)} aspects × {len(MODELS)} models = {total_images} total images")
        log(f"🔄 All images will be processed in parallel with validation")
        log(f"{'=' * 80}\n")
        
        phase23_start = time.time()
        uploaded_files = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for aspect_name, (width, height) in aspect_ratios.items():
                for model in MODELS:
                    # Get pre-generated prompt for this model
                    model_prompt = model_prompts.get(model['name'], user_description)
                    
                    log(f"🚀 Queueing: {model['display_name']} - {aspect_name}")
                    
                    future = executor.submit(
                        process_single_model_aspect_with_validation,
                        task_id, model, aspect_name, width, height,
                        original_image_url, image_url, user_description, model_prompt
                    )
                    futures.append((future, model['display_name'], aspect_name))
            
            log(f"\n{'─' * 80}")
            log(f"⏳ Waiting for all {len(futures)} tasks to complete...")
            log(f"{'─' * 80}\n")
            
            completed = 0
            for future, model_display, aspect in futures:
                result = future.result()
                completed += 1
                if result:
                    uploaded_files.append(result)
                    log(f"✅ [{completed}/{len(futures)}] Completed: {model_display} - {aspect}")
                else:
                    log(f"❌ [{completed}/{len(futures)}] Failed: {model_display} - {aspect}")
        
        phase23_time = time.time() - phase23_start
        
        log(f"\n{'=' * 80}")
        log(f"✅ PHASE 2+3 COMPLETE")
        log(f"📊 Successfully uploaded: {len(uploaded_files)}/{total_images} images")
        log(f"⏱️ Time: {phase23_time:.2f}s")
        log(f"{'=' * 80}\n")
        
        # Uncheck field after ALL uploads
        update_custom_field(task_id, checked=False)
        
        total_time = time.time() - (phase1_start if 'phase1_start' in locals() else time.time())
        
        log(f"\n{'#' * 80}")
        log(f"{'#' * 80}")
        log(f"✅ TASK COMPLETED SUCCESSFULLY!")
        log(f"📊 SUMMARY:")
        log(f"  • Task ID: {task_id}")
        log(f"  • Images created: {len(uploaded_files)}/{total_images}")
        log(f"  • Total time: {total_time:.2f}s")
        log(f"  • Phase 1 (prompts): {phase1_time:.2f}s")
        log(f"  • Phase 2+3 (gen+val): {phase23_time:.2f}s")
        log(f"{'#' * 80}")
        log(f"{'#' * 80}\n")
        
        # 🔓 Release lock on success
        try:
            redis_client = redis.from_url(config.REDIS_URL)
            redis_client.delete(f"task_lock:{task_id}")
            log(f"🔓 Lock released for task {task_id}")
        except Exception as lock_error:
            log(f"⚠️ Warning: Could not release lock: {lock_error}", "WARNING")
        
        return {"status": "success", "task_id": task_id, "images_created": len(uploaded_files)}
        
    except Exception as e:
        log(f"\n{'#' * 80}")
        log(f"❌ TASK FAILED: {task_id}", "ERROR")
        log(f"❌ Error: {e}", "ERROR")
        log(f"{'#' * 80}\n")
        
        # 🔓 Release lock on failure too
        try:
            redis_client = redis.from_url(config.REDIS_URL)
            redis_client.delete(f"task_lock:{task_id}")
            log(f"🔓 Lock released for task {task_id} (after failure)")
        except Exception as lock_error:
            log(f"⚠️ Warning: Could not release lock: {lock_error}", "WARNING")
        
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))