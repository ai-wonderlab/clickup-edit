"""Main FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import health, webhooks
from .providers import OpenRouterClient, WaveSpeedAIClient, ClickUpClient
from .core import PromptEnhancer, ImageGenerator, Validator, Refiner, HybridFallback, Orchestrator
from .utils.config import load_config, get_config
from .utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.
    
    Initializes all clients and components on startup,
    closes them on shutdown.
    """
    # Startup
    logger.info("Application starting up...")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Initialize provider clients
        openrouter = OpenRouterClient(
            api_key=config.openrouter_api_key,
            timeout=config.processing.timeout_seconds if config.processing else 60.0,
        )
        await openrouter.initialize()
        
        wavespeed = WaveSpeedAIClient(
            api_key=config.wavespeed_api_key,
            timeout=120.0,  # Longer timeout for image generation
        )
        await wavespeed.initialize()
        
        clickup = ClickUpClient(
            api_key=config.clickup_api_key,
            timeout=30.0,
        )
        await clickup.initialize()
        
        logger.info("Provider clients initialized")
        
        # Initialize core components
        model_names = [m.name for m in config.image_models]
        
        enhancer = PromptEnhancer(
            openrouter_client=openrouter,
            model_names=model_names,
        )
        await enhancer.load_deep_research()
        
        generator = ImageGenerator(
            wavespeed_client=wavespeed,
        )
        
        validator = Validator(
            openrouter_client=openrouter,
        )
        validator.load_validation_prompt()
        
        refiner = Refiner(
            enhancer=enhancer,
            generator=generator,
            validator=validator,
        )
        
        hybrid_fallback = HybridFallback(
            clickup_client=clickup,
        )
        
        max_iterations = config.processing.max_iterations if config.processing else 3
        
        orchestrator = Orchestrator(
            enhancer=enhancer,
            generator=generator,
            validator=validator,
            refiner=refiner,
            hybrid_fallback=hybrid_fallback,
            max_iterations=max_iterations,
        )
        
        logger.info("Core components initialized")
        
        # Store in app state for access in routes
        app.state.config = config
        app.state.openrouter = openrouter
        app.state.wavespeed = wavespeed
        app.state.clickup = clickup
        app.state.enhancer = enhancer
        app.state.generator = generator
        app.state.validator = validator
        app.state.refiner = refiner
        app.state.hybrid_fallback = hybrid_fallback
        app.state.orchestrator = orchestrator
        
        logger.info("Application startup complete")
        
        yield
        
        # Shutdown
        logger.info("Application shutting down...")
        
        # Close provider clients
        await openrouter.close()
        await wavespeed.close()
        await clickup.close()
        
        logger.info("Application shutdown complete")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


# Create FastAPI application
app = FastAPI(
    title="Image Edit Agent",
    description="Automated image editing agent with parallel AI models",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(webhooks.router, prefix="/webhook", tags=["webhooks"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "image-edit-agent",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )