import os


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://ludex:ludex@localhost:5432/ludex",
)
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")
