from fastapi import FastAPI
from auth.github_oauth import router as github_oauth_router
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.include_router(github_oauth_router, prefix="/auth/github", tags=["auth"])


@app.get("/")
async def root():
    return {"message": "Hello World"}