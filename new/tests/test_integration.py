"""Integration tests for the orchestrator."""

import pytest

from src.models.enums import ProcessStatus


@pytest.mark.asyncio
async def test_enhancer_single_model(enhancer, sample_prompt):
    """Test single model enhancement."""
    result = await enhancer.enhance_single(
        original_prompt=sample_prompt,
        model_name="seedream-v4",
    )
    
    assert result.model_name == "seedream-v4"
    assert result.original == sample_prompt
    assert len(result.enhanced) > len(result.original)
    assert "preserve" in result.enhanced.lower() or "greek" in result.enhanced.lower()


@pytest.mark.asyncio
async def test_enhancer_parallel(enhancer, sample_prompt):
    """Test parallel enhancement across all models."""
    results = await enhancer.enhance_all_parallel(sample_prompt)
    
    assert len(results) >= 1  # At least one should succeed
    assert all(hasattr(r, "enhanced") for r in results)
    assert all(len(r.enhanced) > 0 for r in results)
    
    # Verify different models
    model_names = {r.model_name for r in results}
    assert len(model_names) == len(results)  # All different models


@pytest.mark.asyncio
@pytest.mark.skipif(
    True,  # Skip by default - requires real image
    reason="Requires real image URL and API credits"
)
async def test_full_pipeline(orchestrator, sample_prompt, sample_image_url):
    """Test complete pipeline with real processing."""
    result = await orchestrator.process_with_iterations(
        task_id="test_123",
        prompt=sample_prompt,
        original_image_url=sample_image_url,
    )
    
    # Should either succeed or fallback
    assert result.status in [ProcessStatus.SUCCESS, ProcessStatus.HYBRID_FALLBACK]
    
    if result.status == ProcessStatus.SUCCESS:
        assert result.final_image is not None
        assert result.model_used is not None
        assert result.iterations >= 1
    else:
        assert result.iterations == orchestrator.max_iterations


def test_validation_parsing(validator):
    """Test validation response parsing."""
    sample_response = """
    PASS/FAIL: PASS
    SCORE: 95
    ISSUES:
    - None
    REASONING: All requirements met, Greek text preserved correctly with diacritics intact.
    """
    
    result = validator._parse_validation_response(
        sample_response,
        "seedream-v4"
    )
    
    assert result.passed == True
    assert result.score == 95
    assert result.model_name == "seedream-v4"