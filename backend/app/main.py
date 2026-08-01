from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_database_session
from app.profiles import router as profiles_router

app = FastAPI(
    title="Ludex API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router)


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
