from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.agent.generative_ui import GenerativeUIComposer, GenerativeUIRegistry
from app.agent.orchestrator import FoundationOrchestrator
from app.agent.providers.scripted import ScriptedLLMProvider
from app.agent.registrations import (
    register_conversational_sale_tools,
    register_sale_confirmed_ui,
    register_sale_item_added_ui,
    register_sale_summary_ui,
)
from app.agent.tools import ToolRegistry
from app.api.middleware import CorrelationMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.lumo import router as lumo_router
from app.api.routes.platform import router as platform_router
from app.api.schemas.errors import app_error_handler, http_exception_handler, unhandled_error_handler, validation_error_handler
from app.application.pending import InMemoryPendingClarificationStore
from app.application.workflows.outcomes import EmptyOutcomeEngine
from app.bootstrap.settings import AppEnv, Settings, get_settings
from app.domain.shared.errors import AppError
from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
from app.infrastructure.persistence.seed import ensure_carrota_seed
from app.infrastructure.telemetry import configure_logging
from app.policies.engine import build_policy_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)

    tools = ToolRegistry()
    register_conversational_sale_tools(tools)
    ui_registry = GenerativeUIRegistry()
    register_sale_item_added_ui(ui_registry)
    register_sale_summary_ui(ui_registry)
    register_sale_confirmed_ui(ui_registry)
    policies = build_policy_engine()
    provider = ScriptedLLMProvider()
    orchestrator = FoundationOrchestrator(
        provider=provider,
        tools=tools,
        policies=policies,
    )

    app = FastAPI(title="Lumo API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.app_env = settings.app_env.value
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.tool_registry = tools
    app.state.generative_ui_registry = ui_registry
    app.state.generative_ui_composer = GenerativeUIComposer(ui_registry)
    app.state.orchestrator = orchestrator
    app.state.outcome_engine = EmptyOutcomeEngine()
    app.state.llm_provider = provider
    app.state.policies = policies
    app.state.carrota_token = None
    app.state.pending_clarifications = InMemoryPendingClarificationStore()

    if settings.app_env is AppEnv.LOCAL:
        seed_session = session_factory()
        try:
            _tenant, token = ensure_carrota_seed(seed_session, token_secret=settings.dev_token_secret)
            seed_session.commit()
            app.state.carrota_token = token
            logging.getLogger("lumo.seed").info("carrota seed ready")
        except Exception:
            seed_session.rollback()
            raise
        finally:
            seed_session.close()

    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health_router)
    app.include_router(platform_router)
    app.include_router(lumo_router)

    if settings.app_env.value == "test":
        from pydantic import BaseModel

        class EchoPayload(BaseModel):
            name: str

        @app.get("/api/v1/_test/fail")
        def _fail() -> None:
            raise RuntimeError("intentional failure")

        @app.post("/api/v1/_test/echo")
        def _echo(payload: EchoPayload) -> dict[str, str]:
            return {"name": payload.name}

    return app


def asgi_app() -> FastAPI:
    return create_app()
