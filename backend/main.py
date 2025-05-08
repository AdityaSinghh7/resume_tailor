from fastapi import FastAPI
from dotenv import load_dotenv
import os
import logging
logging.basicConfig(level=logging.INFO)

env_path = os.path.join(os.path.dirname(__file__), '.env')
print("Loading .env from:", env_path)
load_dotenv(dotenv_path=env_path)
from auth.github_oauth import router as github_oauth_router
print("Loaded GITHUB_CLIENT_ID:", os.getenv("GITHUB_CLIENT_ID"))
app = FastAPI()


app.include_router(github_oauth_router, prefix="/auth/github", tags=["auth"])

@app.get("/")
async def root():
    return {"message": "Hello World"}