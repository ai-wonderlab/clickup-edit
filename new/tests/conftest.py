"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
from typing import AsyncGenerator

from src.providers import OpenRouterClient, WaveSpeedAIClient, ClickUpClient
from src.core import PromptEnhancer, ImageGenerator, Validator
from src.utils.config import load_config


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config():
    """Load configuration once for all tests."""
    return load_config()


@pytest.fixture
async def openrouter_client(config) -> AsyncGenerator[OpenRouterClient, None]:
    """Create and initialize OpenRouter client."""
    client = OpenRouterClient(api_key=config.openrouter_api_key)
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
async def wavespeed_client(config) -> AsyncGenerator[WaveSpeedAIClient, None]:
    """Create and initialize WaveSpeedAI client."""
    client = WaveSpeedAIClient(api_key=config.wavespeed_api_key)
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
async def clickup_client(config) -> AsyncGenerator[ClickUpClient, None]:
    """Create and initialize ClickUp client."""
    client = ClickUpClient(api_key=config.clickup_api_key)
    await client.initialize()
    yield client
    await client.close()


@pytest.fixture
async def enhancer(openrouter_client, config):
    """Create PromptEnhancer with loaded research."""
    model_names = [m.name for m in config.image_models]
    enhancer = PromptEnhancer(openrouter_client, model_names)
    await enhancer.load_deep_research()
    return enhancer


@pytest.fixture
async def generator(wavespeed_client):
    """Create ImageGenerator."""
    return ImageGenerator(wavespeed_client)


@pytest.fixture
async def validator(openrouter_client):
    """Create Validator with loaded prompt."""
    validator = Validator(openrouter_client)
    validator.load_validation_prompt()
    return validator


# Sample test data
@pytest.fixture
def sample_prompt():
    """Sample edit prompt for testing."""
    return "Remove background while preserving all Greek text and diacritics"


@pytest.fixture
def sample_image_url():
    """Sample image URL for testing."""
    return "https://example.com/test-image.jpg"