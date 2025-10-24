#!/usr/bin/env python3
"""
FAST TEST SCRIPT - OpenRouter API Validation Issue
Tests the exact scenario causing failures
"""

import httpx
import base64
import json
import sys
from pathlib import Path

# ============================================================================
# CONFIGURATION - CHANGE THESE
# ============================================================================
OPENROUTER_API_KEY = "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"  # ⚠️ PUT YOUR KEY HERE
BASE_URL = "https://openrouter.ai/api/v1"

# Test with a small image (will be created as 100x100 px dummy)
def create_dummy_image() -> bytes:
    """Create tiny PNG for testing"""
    from PIL import Image
    import io
    
    img = Image.new('RGB', (100, 100), color='red')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


# ============================================================================
# TEST 1: Enhancement Request (που δουλεύει)
# ============================================================================
def test_enhancement():
    print("\n" + "="*80)
    print("TEST 1: ENHANCEMENT REQUEST (like your working code)")
    print("="*80)
    
    try:
        # Create dummy image
        img_bytes = create_dummy_image()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this test image briefly."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 200,
            "reasoning": {
                "effort": "medium"
            },
            "provider": {
                "order": ["Anthropic"],
                "allow_fallbacks": False
            }
        }
        
        print(f"📤 Sending enhancement request...")
        print(f"   - Model: {payload['model']}")
        print(f"   - Image size: {len(img_bytes)} bytes")
        print(f"   - Has reasoning: YES")
        print(f"   - Messages: {len(payload['messages'])}")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://test.com",
                    "X-Title": "Test Script"
                }
            )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"   - Model used: {data.get('model', 'unknown')}")
            print(f"   - Response: {data['choices'][0]['message']['content'][:100]}...")
            return True
        else:
            print(f"❌ FAILED!")
            print(f"   - Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False


# ============================================================================
# TEST 2: Validation Request (που αποτυγχάνει)
# ============================================================================
def test_validation():
    print("\n" + "="*80)
    print("TEST 2: VALIDATION REQUEST (like your failing code)")
    print("="*80)
    
    try:
        # Create 2 dummy images (original + edited)
        original_bytes = create_dummy_image()
        edited_bytes = create_dummy_image()
        
        original_b64 = base64.b64encode(original_bytes).decode('utf-8')
        edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
        
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a validation assistant."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Compare these two images. Return JSON with score 0-10."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{original_b64}"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{edited_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 2000,
            # ⚠️ NO REASONING - Like your validation code
            "provider": {
                "order": ["Anthropic"],
                "allow_fallbacks": False
            }
        }
        
        print(f"📤 Sending validation request...")
        print(f"   - Model: {payload['model']}")
        print(f"   - Original image: {len(original_bytes)} bytes")
        print(f"   - Edited image: {len(edited_bytes)} bytes")
        print(f"   - Total images: 2")
        print(f"   - Has reasoning: NO ⚠️")
        print(f"   - Messages: {len(payload['messages'])}")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://test.com",
                    "X-Title": "Test Script"
                }
            )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"   - Model used: {data.get('model', 'unknown')}")
            print(f"   - Response: {data['choices'][0]['message']['content'][:100]}...")
            return True
        else:
            print(f"❌ FAILED!")
            print(f"   - Status: {response.status_code}")
            print(f"   - Error: {response.text[:500]}")
            
            # Try to parse error
            try:
                error_data = response.json()
                print(f"\n🔍 DETAILED ERROR:")
                print(json.dumps(error_data, indent=2))
            except:
                pass
            
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 3: Validation WITH reasoning (το fix)
# ============================================================================
def test_validation_with_reasoning():
    print("\n" + "="*80)
    print("TEST 3: VALIDATION WITH REASONING (the fix)")
    print("="*80)
    
    try:
        original_bytes = create_dummy_image()
        edited_bytes = create_dummy_image()
        
        original_b64 = base64.b64encode(original_bytes).decode('utf-8')
        edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
        
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a validation assistant."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Compare these two images. Return JSON with score 0-10."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{original_b64}"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{edited_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 2000,
            # ✅ ADD REASONING
            "reasoning": {
                "effort": "low"
            },
            "provider": {
                "order": ["Anthropic"],
                "allow_fallbacks": False
            }
        }
        
        print(f"📤 Sending validation WITH reasoning...")
        print(f"   - Model: {payload['model']}")
        print(f"   - Total images: 2")
        print(f"   - Has reasoning: YES ✅")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://test.com",
                    "X-Title": "Test Script"
                }
            )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"   - Model used: {data.get('model', 'unknown')}")
            return True
        else:
            print(f"❌ FAILED!")
            print(f"   - Error: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("\n" + "🔍 OPENROUTER API VALIDATION TEST SCRIPT")
    print("=" * 80)
    
    if OPENROUTER_API_KEY == "YOUR_API_KEY_HERE":
        print("❌ ERROR: Set your OpenRouter API key first!")
        print("   Edit line 15 in the script")
        sys.exit(1)
    
    # Check PIL
    try:
        from PIL import Image
    except ImportError:
        print("❌ ERROR: Install Pillow first:")
        print("   pip install Pillow")
        sys.exit(1)
    
    results = {
        "enhancement": test_enhancement(),
        "validation": test_validation(),
        "validation_with_reasoning": test_validation_with_reasoning()
    }
    
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print(f"Test 1 (Enhancement):              {'✅ PASS' if results['enhancement'] else '❌ FAIL'}")
    print(f"Test 2 (Validation):                {'✅ PASS' if results['validation'] else '❌ FAIL'}")
    print(f"Test 3 (Validation + Reasoning):    {'✅ PASS' if results['validation_with_reasoning'] else '❌ FAIL'}")
    
    print("\n💡 DIAGNOSIS:")
    if results['enhancement'] and not results['validation'] and results['validation_with_reasoning']:
        print("✅ CONFIRMED: Adding 'reasoning' field to validation fixes the issue!")
        print("   → Update your validation code to include reasoning parameter")
    elif not results['enhancement']:
        print("❌ Your OpenRouter API key or Anthropic access has issues")
    elif results['validation']:
        print("✅ Validation works fine - issue might be elsewhere")
    else:
        print("❓ Unclear - check the detailed errors above")
    
    print("\n")


if __name__ == "__main__":
    main()