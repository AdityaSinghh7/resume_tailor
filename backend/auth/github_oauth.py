from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx
import os

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_CALLBACK_URL = os.getenv("GITHUB_OAUTH_CALLBACK_URL")  # e.g., http://localhost:8000/auth/github/callback

@router.get("/login")
def login_with_github():
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_OAUTH_CALLBACK_URL}"
        f"&scope=read:user,user:email,repo"
    )
    return {"auth_url": github_auth_url}

@router.get("/callback")
async def github_callback(request: Request, code: str = None):
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    async with httpx.AsyncClient() as client:
        print("GITHUB_CLIENT_ID: ", GITHUB_CLIENT_ID)
        print("GITHUB_CLIENT_SECRET: ", GITHUB_CLIENT_SECRET)
        print("GITHUB_OAUTH_CALLBACK_URL: ", GITHUB_OAUTH_CALLBACK_URL)
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
        print("access_token: ", access_token)
        print("token_data: ", token_data)
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        # Optionally: fetch user info here
        # user_resp = await client.get(
        #     "https://api.github.com/user",
        #     headers={"Authorization": f"token {access_token}"}
        # )
        # user_data = await user_resp.json()
        frontend_home_url = f"http://localhost:3000/home?access_token={access_token}"
        return RedirectResponse(url=frontend_home_url)
    
    
