from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_database_session
from app.session_routes import router as session_router

from app.recommendations.routes import (
    router as recommendations_router,
)

app = FastAPI(
    title="Ludex API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommendations_router)
app.include_router(session_router)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable_handler(
    _request: Request,
    _error: SQLAlchemyError,
) -> JSONResponse:
    """Return one safe response for database failures outside recommendations."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Ludex is temporarily unavailable."},
    )


@app.get("/health")
def health_check(
    database_session: Session = Depends(get_database_session),
) -> dict[str, str]:
    """Verify that the API can execute a database query.

    Args:
        database_session: The request-scoped database session.

    Returns:
        A health status confirming the API and database connection.

    Raises:
        SQLAlchemyError: If the database cannot execute the health query.
    """
    database_session.execute(text("SELECT 1"))

    return {
        "status": "healthy",
        "database": "connected",
    }
