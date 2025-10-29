"""Test script to verify configuration loading from config.yaml."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config import load_config, get_config


def test_config_loading():
    """Test configuration loading and value access."""
    
    print("=" * 60)
    print("Testing Configuration Loading")
    print("=" * 60)
    
    # Load config
    print("\n1. Loading configuration...")
    config = load_config()
    print("✅ Configuration loaded successfully")
    
    # Test rate limits
    print("\n2. Rate Limit Settings:")
    print(f"   - Enhancement: {config.rate_limit_enhancement}")
    print(f"   - Validation: {config.rate_limit_validation}")
    
    # Test timeouts
    print("\n3. Timeout Settings:")
    print(f"   - OpenRouter: {config.timeout_openrouter_seconds}s")
    print(f"   - WaveSpeed: {config.timeout_wavespeed_seconds}s")
    print(f"   - ClickUp: {config.timeout_clickup_seconds}s")
    print(f"   - WaveSpeed Polling: {config.timeout_wavespeed_polling_seconds}s")
    
    # Test validation settings
    print("\n4. Validation Settings:")
    print(f"   - Delay: {config.validation_delay_seconds}s")
    print(f"   - Pass Threshold: {config.validation_pass_threshold}")
    
    # Test ClickUp settings
    print("\n5. ClickUp Settings:")
    print(f"   - Custom Field ID: {config.clickup_custom_field_id_ai_edit}")
    print(f"   - Status Complete: {config.clickup_status_complete}")
    print(f"   - Status Blocked: {config.clickup_status_blocked}")
    print(f"   - Status Needs Review: {config.clickup_status_needs_review}")
    
    # Test locking settings
    print("\n6. Locking Settings:")
    print(f"   - TTL: {config.lock_ttl_seconds}s")
    print(f"   - Cleanup Interval: {config.lock_cleanup_interval}")
    
    # Test processing settings
    print("\n7. Processing Settings:")
    print(f"   - Max Iterations: {config.max_iterations}")
    
    # Test model configuration
    print("\n8. Image Models:")
    for model in config.image_models:
        print(f"   - {model.name} (priority: {model.priority})")
    
    # Test environment
    print("\n9. Environment:")
    print(f"   - App Env: {config.app_env}")
    
    print("\n" + "=" * 60)
    print("✅ All Configuration Tests Passed!")
    print("=" * 60)
    
    # Test get_config() returns same instance
    print("\n10. Testing get_config() singleton...")
    config2 = get_config()
    assert config is config2, "get_config() should return same instance"
    print("✅ Singleton pattern working correctly")
    
    return config


if __name__ == "__main__":
    try:
        test_config_loading()
    except Exception as e:
        print(f"\n❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
