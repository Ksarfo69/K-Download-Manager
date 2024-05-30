from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import Base
from app.routes import router
from app.services.db_service import engine

# Create engine
Base.metadata.create_all(engine)

app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

# Allow all origins, methods, headers
app.add_middleware(
    CORSMiddleware,
    allow_origins='*',
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)