from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import RedirectResponse
import httpx
import os
from db import get_db_pool
from models import UserCreate
from auth.jwt import create_access_token, verify_access_token, get_current_user_from_token
import logging
from data_ingestion.github_ingestion import GitHubIngestionService
import asyncio
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")

@router.get("/login")
async def login_with_github():
    """Redirect to GitHub for OAuth login."""
    return RedirectResponse(
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_OAUTH_CALLBACK_URL}"
        f"&scope=read:user,user:email,repo"
    )

@router.get("/callback")
async def github_callback(code: str):
    """Handle GitHub OAuth callback."""
    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code
                },
                headers={"Accept": "application/json"}
            )
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                logger.error("Failed to get access token from GitHub")
                raise HTTPException(status_code=400, detail="Failed to get access token")

            # Get user information
            user_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}"}
            )
            user_data = user_response.json()
            username = user_data.get("login")
            
            if not username:
                logger.error("Failed to get user data from GitHub")
                raise HTTPException(status_code=400, detail="Failed to get user data")

            # Store user in database
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("""
                    INSERT INTO users (username, access_code)
                    VALUES ($1, $2)
                    ON CONFLICT (username) DO UPDATE
                    SET access_code = EXCLUDED.access_code
                    RETURNING uid
                """, username, access_token)
                
                logger.info(f"Stored user {username} with ID {user_id}")

            # Create JWT token
            jwt_token = jwt.encode(
                {
                    "sub": username,
                    "exp": datetime.utcnow() + timedelta(days=1)
                },
                JWT_SECRET,
                algorithm="HS256"
            )

            # Start repository ingestion in background
            logger.info(f"Starting repository ingestion for user {username}")
            ingestion_service = GitHubIngestionService(access_token)
            
            # Get user's repositories
            repos = await ingestion_service.fetch_user_repositories()
            logger.info(f"Found {len(repos)} repositories for user {username}")
            
            # Process each repository
            for repo in repos:
                try:
                    repo_name = repo["full_name"]
                    logger.info(f"Processing repository: {repo_name}")
                    await ingestion_service.process_repository(user_id, repo_name)
                except Exception as e:
                    logger.error(f"Error processing repository {repo_name}: {str(e)}")
                    continue

            # Redirect to frontend with token
            redirect_url = f"{FRONTEND_URL}/home?token={jwt_token}"
            logger.info(f"Redirecting to: {redirect_url}")
            return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Error in GitHub callback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me")
async def get_current_user(authorization: str = Header(None)):
    """Get current user information."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header")
    
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        username = payload.get("sub")
        
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return {"username": username}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) 