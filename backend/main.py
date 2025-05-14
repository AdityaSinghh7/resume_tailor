from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routers
from auth.github_oauth import router as auth_router
# from routes.repository_routes import router as repository_router
from api.repositories import router as repository_router
from api.repository_processing import router as processing_router

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth/github", tags=["auth"])
app.include_router(repository_router, prefix="/api", tags=["repositories"])
app.include_router(processing_router, prefix="/api", tags=["processing"])

@app.get("/")
async def root():
    return {"message": "Hello World"}