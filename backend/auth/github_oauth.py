from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import RedirectResponse
import httpx
import os
from db import get_db_pool
from models import UserCreate
from auth.jwt import create_access_token, verify_access_token
import logging
from data_ingestion.github_ingestion import GitHubIngestionService
import asyncio

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL")  # e.g., http://localhost:8000/auth/github/callback

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

async def get_current_user_from_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ")[1]
    payload = verify_access_token(token)
    return payload

@router.get("/login")
def login_with_github():
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_OAUTH_CALLBACK_URL}"
        f"&scope=read:user,user:email,repo"
    )
    return RedirectResponse(github_auth_url)

async def fetch_and_store_all_repos(user_id, access_code):
    try:
        ingestion_service = GitHubIngestionService(access_code)
        repos = await ingestion_service.fetch_user_repositories()
        # Only process public repositories
        public_repos = [repo for repo in repos if not repo.get('private', False)]
        tasks = [
            ingestion_service.fetch_and_store_repo_files_metadata(user_id, repo, max_file_size=200_000)
            for repo in public_repos
        ]
        await asyncio.gather(*tasks)
    except Exception as e:
        logging.error(f"Error during repo metadata ingestion: {e}")

@router.get("/callback")
async def github_callback(request: Request, code: str = None):
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_CALLBACK_URL,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        # Optionally: fetch user info here
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {access_token}"}
        )
        user_data = user_resp.json()
        username = user_data["login"]
        access_code = access_token

    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Upsert user
            await conn.execute("""
                INSERT INTO users (username, access_code)
                VALUES ($1, $2)
                ON CONFLICT (username) DO UPDATE SET access_code = EXCLUDED.access_code
            """, username, access_code)

            row = await conn.fetchrow("SELECT uid FROM users WHERE username = $1", username)
            user_id = row["uid"]

            jwt_token = create_access_token({"uid": user_id})
    except Exception as e:
        logging.error(f"Error during user upsert or token creation: {e}")
        raise HTTPException(status_code=500, detail="User authentication failed.")

    # Only call ingestion if user upsert and token creation succeeded
    asyncio.create_task(fetch_and_store_all_repos(user_id, access_code))

    redirect_url = f"{FRONTEND_URL}/home?access_token={jwt_token}"
    return RedirectResponse(redirect_url, status_code=302)

@router.get("/me")
async def get_current_user(payload: dict = Depends(get_current_user_from_token)):
    user_id = payload["uid"]
    logging.info(f"JWT payload: {payload}")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", user_id)
        if row:
            logging.info(f"User found for uid {user_id}: {dict(row)}")
            return dict(row)
        else:
            logging.warning(f"User not found for uid {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
    
    
