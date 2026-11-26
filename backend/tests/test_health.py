"""Phase 1: API health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        unauthorized = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert unauthorized.status_code == 401
