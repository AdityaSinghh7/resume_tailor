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
from auth.supabase_auth import router as supabase_auth_router
# from routes.repository_routes import router as repository_router
from api.repositories import router as repository_router
from api.repository_processing import router as processing_router
from api.rag import router as rag_router

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
app.include_router(supabase_auth_router, prefix="/auth/supabase", tags=["auth"])
app.include_router(repository_router, prefix="/api", tags=["repositories"])
app.include_router(processing_router, prefix="/api", tags=["processing"])
app.include_router(rag_router, prefix="/api", tags=["rag"])

@app.get("/")
async def root():
    return {"message": "Hello World"}
