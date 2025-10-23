"""Abstract base class for API providers."""

from abc import ABC, abstractmethod
import httpx
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class BaseProvider(ABC):
    """Abstract base class for all API providers."""
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
    ):
        """
        Initialize provider.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for API endpoints
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def initialize(self):
        """Initialize the HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._get_default_headers(),
            )
            logger.info(
                f"{self.__class__.__name__} initialized",
                extra={"provider": self.__class__.__name__}
            )
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info(
                f"{self.__class__.__name__} closed",
                extra={"provider": self.__class__.__name__}
            )
    
    @abstractmethod
    def _get_default_headers(self) -> dict:
        """Get default headers for requests."""
        pass
    
    def _ensure_client(self):
        """Ensure client is initialized."""
        if self.client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} not initialized. "
                "Call initialize() or use as async context manager."
            )