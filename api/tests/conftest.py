"""
Shared fixtures for the dg-form API test suite.

The `async_client` fixture patches `main.start_eviction_task` so that the
ASGI lifespan completes without scheduling a real background asyncio.Task.
All fixtures use function scope (the default) so every test gets a clean
transport with its own startup/shutdown cycle.
"""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    # Import here to avoid issues if 'api/' isn't the cwd during collection.
    from main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def async_client(app):
    """Yield an AsyncClient backed by the FastAPI ASGI app.

    start_eviction_task is patched to an AsyncMock so the lifespan completes
    without spawning a live asyncio.Task that would outlive the test.
    """
    with patch("main.start_eviction_task", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
