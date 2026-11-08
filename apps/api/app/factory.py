"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api import __version__
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.database_url import DatabaseUrlError
from apps.api.app.deps import get_current_principal
from apps.api.app.errors import AppError, app_error_handler
from apps.api.app.exchange.binding_api import router as exchange_bindings_router
from apps.api.app.exchange.router import router as exchange_router
from apps.api.app.market_data.router import router as market_public_router
from apps.api.app.market_data.stream_endpoint import router as market_stream_router
from apps.api.app.observability.router import router as observability_router
from apps.api.app.signals.cloud_history_router import router as signals_cloud_router
from apps.api.app.signals.router import router as signals_router
from apps.api.app.automation.router import router as automation_router
from apps.api.app.paper.router import router as paper_router
from apps.api.app.backtests.router import router as backtests_router
from apps.api.app.backtests.run_router import router as backtests_run_router
from apps.api.app.news.router import router as news_router
from apps.api.app.llm.router import router as llm_router
from apps.api.app.routers import catalog, health, me, system


def _print_database_status(settings: ApiSettings) -> None:
    """Startup console status only — never prints passwords or raw DATABASE_URL."""
    if not settings.database_configured:
        print("[db] status=not_configured (DATABASE_URL empty)")
        return
    try:
        info = settings.database_url_info()
        print(
            f"[db] status=connecting "
            f"host={info.host} port={info.port} "
            f"pooler={info.pooler_hint} sslmode={info.sslmode}"
        )
        print(f"[db] url={info.redacted_url}")
        from apps.api.app.db import create_db_engine, ping_database, reset_engine

        reset_engine()
        ping_database(create_db_engine(settings))
        print("[db] status=connected CONNECT_SUCCESS")
    except DatabaseUrlError as exc:
        print(f"[db] status=config_error detail={exc}")
    except Exception as exc:  # noqa: BLE001 — report type only; no connection string
        print(f"[db] status=connect_failed error={type(exc).__name__}")


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or get_api_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _print_database_status(settings)
        from apps.api.app.signals.engine_service import (
            maybe_autoload_engine,
            shutdown_auto_engine,
        )

        maybe_autoload_engine()
        from apps.api.app.news.scheduler_runtime import (
            maybe_start_news_scheduler,
            shutdown_news_scheduler,
        )

        maybe_start_news_scheduler(settings)
        try:
            yield
        finally:
            shutdown_news_scheduler()
            shutdown_auto_engine()
            from apps.api.app.market_data.stream_hub import get_market_stream_hub

            get_market_stream_hub().stop_all()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version or __version__,
        docs_url="/docs" if settings.api_debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.api_debug else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.token_verifier = None
    from apps.api.app.exchange.binding_store import InMemoryBindingStore

    # Tests / processes without DB use in-memory. Production owner-bound reads
    # should use SqlAlchemyBindingStore once migrations are applied.
    fixture_store = InMemoryBindingStore()
    app.state.exchange_binding_fixture_store = fixture_store
    app.state.exchange_binding_store = fixture_store
    app.state.bybit_wallet_clients = {}
    # Routers depend on get_api_settings — pin to this app instance's settings.
    app.dependency_overrides[get_api_settings] = lambda: settings

    app.add_exception_handler(AppError, app_error_handler)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Accept", "Content-Type", "Authorization"],
        )

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(me.router)
    app.include_router(catalog.router)
    app.include_router(observability_router)
    app.include_router(exchange_router)
    app.include_router(exchange_bindings_router)
    app.include_router(market_public_router)
    app.include_router(market_stream_router)
    app.include_router(signals_router)
    app.include_router(signals_cloud_router)
    app.include_router(automation_router)
    app.include_router(paper_router)
    app.include_router(backtests_router)
    app.include_router(backtests_run_router)
    app.include_router(news_router)
    app.include_router(llm_router)
    app.state.bybit_wallet_client = None
    app.state.bybit_public_rest = None
    app.state.bybit_public_ws = None

    @app.get("/")
    def root() -> dict[str, object]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "health": "/health",
            "status": "/api/v1/system/status",
            "me": "/api/v1/me",
            "read_only": True,
            "trading_endpoints": False,
            "private_catalog_reads_enabled": settings.private_data_reads_enabled,
            "observability_fixture_mode": settings.observability_fixture_mode,
            "observability_snapshot": "/api/v1/observability/snapshot",
            "exchange_wallet": "/api/v1/exchange/wallet",
            "exchange_wallet_reads_enabled": settings.exchange_wallet_reads_enabled,
            "exchange_bindings": "/api/v1/exchange/bindings",
            "exchange_binding_persistence_enabled": (
                settings.exchange_binding_persistence_enabled
            ),
            "market_public": "/api/v1/market/meta",
            "market_public_stream": "/api/v1/market/stream",
            "market_public_note": "Bybit V5 public market data only — not private account live",
            "signals": "/api/v1/signals/status",
            "signals_auto_engine": "/api/v1/signals/engine/status",
            "signals_note": "Phase 4C signals-only auto candle engine — no order submission",
            "automation": "/api/v1/automation/status",
            "automation_note": "Phase 6A foundation — SIGNALS_ONLY default; no Mainnet path",
            "paper": "/api/v1/paper/status",
            "paper_read_api_enabled": settings.paper_read_api_enabled,
            "paper_note": (
                "Prompt 65B local paper journal read-only — "
                "PAPER_READ_API_ENABLED default false; no order submission"
            ),
            "backtests": "/api/v1/backtests/status",
            "news": "/api/v1/news/status",
            "backtest_read_api_enabled": settings.backtest_read_api_enabled,
            "backtest_note": (
                "Prompt 68B saved backtest artifact read-only — "
                "BACKTEST_READ_API_ENABLED default false; never executes a backtest"
            ),
        }

    # Compatibility stub: still requires Bearer auth (401 without).
    @app.get("/api/v1/private/disabled", include_in_schema=False)
    def private_disabled(
        _principal=Depends(get_current_principal),
    ) -> dict[str, str]:
        return {"status": "auth_ok_no_private_payload"}

    return app
