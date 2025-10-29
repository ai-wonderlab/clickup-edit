"""ClickUp API client for task and attachment management."""

import httpx
from typing import Any, Optional

from .base import BaseProvider
from ..utils.logger import get_logger
from ..utils.errors import ProviderError, AuthenticationError
from ..utils.retry import retry_async

logger = get_logger(__name__)


class ClickUpClient(BaseProvider):
    """Client for ClickUp API."""
    
    def __init__(self, api_key: str, timeout: Optional[float] = None):
        """
        Initialize ClickUp client.
        
        Args:
            api_key: ClickUp API key
            timeout: Request timeout in seconds (defaults to config value)
        """
        # ✅ NEW: Use config value if not explicitly provided
        if timeout is None:
            from ..utils.config import get_config
            config = get_config()
            timeout = config.timeout_clickup_seconds
        
        super().__init__(
            api_key=api_key,
            base_url="https://api.clickup.com/api/v2",
            timeout=timeout,
        )
    
    def _get_default_headers(self) -> dict:
        """Get default headers for ClickUp requests."""
        return {
            "Authorization": self.api_key,  # ClickUp uses direct API key
        }
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def download_attachment(self, attachment_url: str) -> bytes:
        """
        Download an attachment from ClickUp.
        
        Args:
            attachment_url: Direct URL to the attachment file
            
        Returns:
            Attachment bytes
            
        Raises:
            ProviderError: If download fails
        """
        self._ensure_client()
        
        try:
            logger.info(
                "Downloading attachment from URL",
                extra={"url": attachment_url[:100]}
            )
            
            # Download directly from the URL
            response = await self.client.get(attachment_url)
            response.raise_for_status()
            
            image_bytes = response.content
            
            logger.info(
                "Attachment downloaded",
                extra={"size_kb": len(image_bytes) / 1024}
            )
            
            return image_bytes
            
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                "clickup",
                f"Failed to download attachment: {e}",
                e.response.status_code
            )

    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def upload_attachment(
        self,
        task_id: str,
        image_bytes: bytes,
        filename: str,
    ) -> str:
        """
        Upload an attachment to a ClickUp task.
        
        Args:
            task_id: ClickUp task ID
            image_bytes: Image data
            filename: Filename for the attachment
            
        Returns:
            Attachment ID
            
        Raises:
            ProviderError: If upload fails
        """
        self._ensure_client()
        
        try:
            logger.info(
                "Uploading attachment",
                extra={
                    "task_id": task_id,
                    "file_name": filename,
                    "size_kb": len(image_bytes) / 1024,
                }
            )
            
            # Prepare multipart upload
            files = {
                "attachment": (filename, image_bytes, "image/png"),
            }
            
            # Note: For file upload, we need different headers
            headers = {
                "Authorization": self.api_key,
            }
            
            response = await self.client.post(
                f"{self.base_url}/task/{task_id}/attachment",
                files=files,
                headers=headers,
            )
            
            # Check status first, before trying to parse JSON
            if response.status_code != 200:
                logger.error(
                    f"Upload failed: {response.status_code}",
                    extra={
                        "status": response.status_code,
                        "response_text": response.text[:500],
                    }
                )
                raise ProviderError(
                    "clickup",
                    f"Upload failed: {response.status_code} - {response.text[:200]}",
                    response.status_code
                )
            
            # Try to parse JSON response
            try:
                data = response.json()
                attachment_id = data.get("id")
            except Exception as e:
                # If not JSON, check if upload was successful anyway
                logger.warning(
                    f"Response not JSON, but status 200: {response.text[:200]}",
                    extra={"task_id": task_id}
                )
                # Consider it successful if we got 200
                attachment_id = "uploaded"
            
            logger.info(
                "Attachment uploaded",
                extra={
                    "task_id": task_id,
                    "attachment_id": attachment_id,
                }
            )
            
            return attachment_id
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def update_task_status(
        self,
        task_id: str,
        status: str,
        comment: Optional[str] = None,
    ):
        """
        Update task status and optionally add a comment.
        
        Args:
            task_id: ClickUp task ID
            status: New status
            comment: Optional comment to add
        """
        self._ensure_client()
        
        try:
            # Update status
            logger.info(
                "Updating task status",
                extra={"task_id": task_id, "status": status}
            )
            
            response = await self.client.put(
                f"{self.base_url}/task/{task_id}",
                json={"status": status},
                headers={"Content-Type": "application/json"}
            )
            
            self._handle_response_errors(response)
            
            # Add comment if provided
            if comment:
                await self.add_comment(task_id, comment)
            
            logger.info(
                "Task status updated",
                extra={"task_id": task_id, "status": status}
            )
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here
    
    @retry_async(max_attempts=2, exceptions=(httpx.RequestError,))
    async def add_comment(self, task_id: str, comment_text: str):
        """
        Add a comment to a task.
        
        Args:
            task_id: ClickUp task ID
            comment_text: Comment text
        """
        self._ensure_client()
        
        try:
            logger.info(
                "Adding comment to task",
                extra={"task_id": task_id}
            )
            
            response = await self.client.post(
                f"{self.base_url}/task/{task_id}/comment",
                json={"comment_text": comment_text},
            )
            
            self._handle_response_errors(response)
            
            logger.info(
                "Comment added",
                extra={"task_id": task_id}
            )
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here
    
    @retry_async(max_attempts=2, exceptions=(httpx.RequestError,))
    async def get_task(self, task_id: str) -> dict:
        """
        Get task details.
        
        Args:
            task_id: ClickUp task ID
            
        Returns:
            Task data dict
        """
        self._ensure_client()
        
        try:
            response = await self.client.get(
                f"{self.base_url}/task/{task_id}",
            )
            
            self._handle_response_errors(response)
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here

    async def update_custom_field(
        self,
        task_id: str,
        field_id: str,
        value: Optional[Any],
    ):
        """Update a custom field value."""
        url = f"{self.base_url}/task/{task_id}/field/{field_id}"
        
        payload = {"value": value}
        
        response = await self.client.post(url, json=payload)
        self._handle_response_errors(response)
        
        logger.info(
            "Custom field updated",
            extra={"task_id": task_id, "field_id": field_id}
        )
    
    def _handle_response_errors(self, response: httpx.Response):
        """Handle HTTP response errors."""
        if response.status_code == 401:
            raise AuthenticationError("clickup")
        elif response.status_code >= 400:
            try:
                error_data = response.json()
                error_message = error_data.get("err") or error_data.get("error") or response.text
            except:
                error_message = response.text
            
            raise ProviderError(
                "clickup",
                error_message,
                response.status_code
            )