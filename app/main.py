from fastapi import FastAPI
from app.api import router

app = FastAPI(title="AutoDocs Layer 2", version="1.0.0")
app.include_router(router)
