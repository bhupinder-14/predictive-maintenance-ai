from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware

from src.api.main import create_app


def make_cors(monkeypatch: pytest.MonkeyPatch, origin: str | None) -> CORSMiddleware:
    if origin is None:
        monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("FRONTEND_ORIGIN", origin)

    # Read the real FastAPI app's middleware configuration without starting
    # lifespan, loading models, or initializing a database.
    app = create_app(database_url="sqlite:///:memory:")
    configured = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    async def endpoint(_scope, _receive, _send) -> None:
        return None

    return CORSMiddleware(endpoint, **configured.kwargs)


def test_cors_allows_only_exact_configured_origin_and_required_methods_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_origin = "https://portfolio.example"
    middleware = make_cors(monkeypatch, allowed_origin)

    assert middleware.is_allowed_origin(allowed_origin)
    assert not middleware.is_allowed_origin("https://other.example")
    assert middleware.allow_credentials is False
    assert middleware.allow_methods == ["GET", "POST"]
    assert {"accept", "content-type"}.issubset(middleware.allow_headers)
    assert middleware.allow_all_origins is False


def test_cors_is_disabled_when_frontend_origin_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middleware = make_cors(monkeypatch, None)

    assert middleware.allow_origins == []
    assert not middleware.is_allowed_origin("http://127.0.0.1:5173")


@pytest.mark.parametrize(
    "origin",
    ["*", "https://site.example/path", "ftp://site.example", "https://user@site.example"],
)
def test_cors_rejects_non_origin_or_wildcard_configuration(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", origin)

    with pytest.raises(ValueError, match="FRONTEND_ORIGIN"):
        create_app(database_url="sqlite:///:memory:")
