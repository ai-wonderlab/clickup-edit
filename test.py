#!/usr/bin/env python3
"""
Direct Wavespeed Test WITH Claude Validation
"""
import os
import sys
import time
import json
import logging
import requests
from io import BytesIO
from datetime import datetime, timedelta
from threading import Lock
import hashlib
from config import config
from file_converters import convert_to_png

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Proxy token management
proxy_tokens = {}
proxy_lock = Lock()

def create_proxy_url(private_url):
    """Create temporary public URL for validation"""
    with proxy_lock:
        token_data = f"{private_url}{datetime.now()}{os.urandom(16)}"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:32]
        
        proxy_tokens[token] = {
            'url': private_url,
            'expires': datetime.now() + timedelta(minutes=15),
        }
        
        proxy_base = config.PROXY_BASE_URL
        return f"{proxy_base}/proxy/image/{token}"

def get_proxy_token_data(token):
    """Get data for a proxy token"""
    with proxy_lock:
        return proxy_tokens.get(token)

def upload_to_uguu(image_path):
    """Upload image to uguu.se"""
    logger.info(f"📤 Uploading to uguu.se...")
    
    # Convert to PNG if needed
    with open(image_path, 'rb') as f:
        file_bytes = f.read()
    
    if image_path.lower().endswith('.psd'):
        logger.info("Converting PSD to PNG...")
        png_bytes = convert_to_png(file_bytes, os.path.basename(image_path))
        if not png_bytes:
            logger.error("Failed to convert PSD")
            return None
    else:
        png_bytes = file_bytes
    
    try:
        response = requests.post(
            'https://uguu.se/upload.php',
            files={'files[]': ('image.png', png_bytes, 'image/png')}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('files'):
                url = data['files'][0]['url']
                url = url.replace('\\/', '/')
                logger.info(f"✅ Uploaded: {url}")
                return url
    except Exception as e:
        logger.error(f"Upload error: {e}")
    return None

def validate_with_claude(original_url, generated_url, user_prompt, model_name):
    """Validate using Claude via proxy URLs"""
    logger.info(f"\n🔍 === CLAUDE VALIDATION ===")
    
    # Create proxy URLs that Claude can access
    original_proxy = create_proxy_url(original_url)
    generated_proxy = create_proxy_url(generated_url)
    
    logger.info(f"📎 Original proxy: {original_proxy}")
    logger.info(f"📎 Generated proxy: {generated_proxy}")
    
    validation_prompt = f"""Compare these two images VERY CAREFULLY.

Original image: First image (the poster with KUDU COFFEE and 20% OFF)
Generated image: Second image (the edited version)

User's edit request was: {user_prompt}

Analyze SPECIFICALLY:
1. Was the KUDU COFFEE logo moved to the right edge? (Yes/No)
2. Was "20%" changed to "30%"? (Yes/No)
3. Was the Greek text changed as requested? (Yes/No)
4. Overall quality and professionalism of the edit?

Score each aspect 0-100 based on whether the edit was actually performed.
If an edit wasn't done at all, score should be 0.

Return JSON only:
{{
  "logo_moved": false,
  "percentage_changed": false,
  "greek_text_changed": false,
  "accuracy_score": 0,
  "quality_score": 0,
  "overall_score": 0,
  "pass": false,
  "reasoning": "Detailed explanation of what was or wasn't done"
}}"""

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.YOUR_SITE_URL,
        "X-Title": "Direct Validation Test"
    }
    
    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": validation_prompt},
                    {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": original_proxy
                        }
                    },
                    {
                        "type": "image", 
                        "source": {
                            "type": "url",
                            "url": generated_proxy
                        }
                    }
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    
    try:
        logger.info(f"📡 Calling Claude API...")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            logger.error(f"❌ Claude API error {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
        
        result = response.json()
        validation_text = result['choices'][0]['message']['content'].strip()
        
        logger.info(f"📝 Raw Claude response: {validation_text[:500]}...")
        
        # Clean and parse JSON
        validation_text = validation_text.replace('```json', '').replace('```', '').strip()
        
        try:
            validation_result = json.loads(validation_text)
            
            logger.info(f"\n📊 === VALIDATION RESULTS ===")
            logger.info(f"✅ Logo moved: {validation_result.get('logo_moved', False)}")
            logger.info(f"✅ Percentage changed: {validation_result.get('percentage_changed', False)}")
            logger.info(f"✅ Greek text changed: {validation_result.get('greek_text_changed', False)}")
            logger.info(f"📊 Overall score: {validation_result.get('overall_score', 0)}/100")
            logger.info(f"💭 Reasoning: {validation_result.get('reasoning', 'N/A')}")
            
            return validation_result
            
        except json.JSONDecodeError as e:
            logger.error(f"⚠️ Could not parse Claude's response as JSON: {e}")
            logger.info(f"Raw response: {validation_text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Validation error: {e}")
        return None

def call_wavespeed_model(image_url, prompt, model_config):
    """Call Wavespeed model"""
    model_name = model_config['name']
    endpoint = model_config['endpoint']
    
    logger.info(f"\n🎨 Testing {model_name}")
    logger.info(f"📝 Prompt: {prompt[:100]}...")
    
    headers = {
        'Authorization': f'Bearer {config.WAVESPEED_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    width, height = 1408, 1408
    
    # Model-specific payload
    if 'qwen-image/edit-plus' in endpoint:
        payload = {
            'images': [image_url],
            'prompt': prompt,
            'seed': -1,
            'size': f'{width}*{height}',
            'output_format': 'png'
        }
    else:
        payload = {
            'image': image_url,
            'prompt': prompt,
            'seed': -1,
            'output_format': 'png'
        }
    
    logger.info(f"🚀 Sending to Wavespeed...")
    
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ API Error {response.status_code}")
            return None
            
        data = response.json()
        job_id = data['data'].get('id')
        get_url = data['data'].get('urls', {}).get('get')
        
        logger.info(f"✅ Job created: {job_id}")
        
        # Poll for result
        status_url = get_url or f"https://api.wavespeed.ai/api/v3/predictions/{job_id}/result"
        
        for attempt in range(60):
            response = requests.get(status_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result_data = response.json()
                
                if 'data' in result_data:
                    status = result_data['data'].get('status')
                    
                    if status == 'completed':
                        outputs = result_data['data'].get('outputs', [])
                        if outputs:
                            logger.info(f"✅ Job completed!")
                            return outputs[0]
                    elif status == 'failed':
                        logger.error(f"❌ Job failed")
                        return None
            
            time.sleep(2)
        
        logger.error(f"⏰ Timeout")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return None

def main():
    """Main test with validation"""
    print("\n" + "="*60)
    print("🧪 WAVESPEED TEST WITH CLAUDE VALIDATION")
    print("="*60)
    
    # Import the proxy function for the app
    from tasks import get_proxy_token_data as gtd
    globals()['get_proxy_token_data'] = gtd
    
    # Get input
    image_path = input("\n📁 Enter image path: ").strip().replace("'", "").replace('"', '')
    
    if not os.path.exists(image_path):
        logger.error(f"❌ File not found")
        sys.exit(1)
    
    print("\n📝 Enter your exact edit instructions:")
    user_prompt = input("> ").strip()
    
    # Upload image
    original_url = upload_to_uguu(image_path)
    if not original_url:
        logger.error("❌ Upload failed")
        sys.exit(1)
    
    # Test with Qwen
    model = {
        'name': 'qwen',
        'endpoint': 'https://api.wavespeed.ai/api/v3/wavespeed-ai/qwen-image/edit',
    }
    
    generated_url = call_wavespeed_model(original_url, user_prompt, model)
    
    if generated_url:
        # Save the result
        img_response = requests.get(generated_url)
        filename = f"test_result_qwen.png"
        with open(filename, 'wb') as f:
            f.write(img_response.content)
        logger.info(f"💾 Saved: {filename}")
        
        # Now validate with Claude
        validation = validate_with_claude(original_url, generated_url, user_prompt, model['name'])
        
        if validation:
            if validation.get('overall_score', 0) >= 90:
                print("\n🎉 PASSED VALIDATION!")
            else:
                print(f"\n❌ FAILED: Score {validation.get('overall_score', 0)}/100")
                print(f"Reason: {validation.get('reasoning', 'Unknown')}")
    else:
        logger.error("❌ Generation failed")

if __name__ == "__main__":
    # Make sure Flask app is running for proxy
    print("⚠️ Make sure your Flask app is running (python3 app.py)")
    input("Press Enter when ready...")
    main()