import os
import logging
import asyncio
import json
import time
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from db import get_db_pool
from data_ingestion.github_ingestion import GitHubIngestionService, project_exists
from api.processing_service import RepositoryProcessingService

logger = logging.getLogger(__name__)

router = APIRouter()

load_dotenv()

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
_supabase_base = SUPABASE_URL.rstrip("/") if SUPABASE_URL else None
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL") or (
    f"{_supabase_base}/auth/v1/keys" if _supabase_base else None
)
SUPABASE_JWKS_FALLBACK_URL = os.getenv("SUPABASE_JWKS_FALLBACK_URL") or (
    f"{_supabase_base}/auth/v1/.well-known/jwks.json" if _supabase_base else None
)
_jwks_cache: Optional[dict] = None
_jwks_cache_ts: float = 0.0
_jwks_cache_ttl = 60 * 60


class SupabaseSessionPayload(BaseModel):
    provider_token: Optional[str] = None


def _fetch_jwks(url: str) -> dict:
    if not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY is not configured.")
    resp = httpx.get(url, headers={"apikey": SUPABASE_ANON_KEY}, timeout=10.0)
    if resp.status_code != 200:
        logger.error("Failed to fetch JWKS from %s: %s", url, resp.text)
        raise HTTPException(status_code=401, detail="Failed to fetch JWKS.")
    return resp.json()


def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cache_ts
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_ts) < _jwks_cache_ttl:
        return _jwks_cache
    if not SUPABASE_JWKS_URL:
        raise HTTPException(status_code=500, detail="SUPABASE_JWKS_URL is not configured.")
    try:
        _jwks_cache = _fetch_jwks(SUPABASE_JWKS_URL)
    except HTTPException:
        if not SUPABASE_JWKS_FALLBACK_URL:
            raise
        _jwks_cache = _fetch_jwks(SUPABASE_JWKS_FALLBACK_URL)
    _jwks_cache_ts = now
    return _jwks_cache


def _get_signing_key_from_jwks(token: str, alg: str):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token header missing kid.")
    jwks = _get_jwks()
    key_dict = next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)
    if not key_dict:
        raise HTTPException(status_code=401, detail="Signing key not found for token.")
    return jwt.algorithms.get_default_algorithms()[alg].from_jwk(json.dumps(key_dict))


def _verify_supabase_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        verify_aud = bool(SUPABASE_JWT_AUD)
        if alg in {"RS256", "ES256"}:
            signing_key = _get_signing_key_from_jwks(token, alg)
            return jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience=SUPABASE_JWT_AUD if verify_aud else None,
                options={"verify_aud": verify_aud},
            )
        if alg == "HS256":
            if not SUPABASE_JWT_SECRET:
                raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not configured.")
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=SUPABASE_JWT_AUD if verify_aud else None,
                options={"verify_aud": verify_aud},
            )
        raise HTTPException(status_code=401, detail="Unsupported token algorithm.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


async def _get_github_username(provider_token: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {provider_token}"},
        )
    if resp.status_code != 200:
        logger.error("GitHub user lookup failed: %s", resp.text)
        raise HTTPException(status_code=401, detail="GitHub token invalid or expired.")
    data = resp.json()
    username = data.get("login")
    if not username:
        raise HTTPException(status_code=400, detail="GitHub username not found.")
    return username


async def _fetch_and_store_all_repos(user_id: int, access_token: str) -> None:
    try:
        ingestion_service = GitHubIngestionService(access_token)
        repos = await ingestion_service.fetch_user_repositories()
        public_repos = [repo for repo in repos if not repo.get("private", False)]
        tasks = []
        for repo in public_repos:
            exists = await project_exists(user_id, repo["html_url"])
            if exists:
                logger.info("Skipping existing project for user %s: %s", user_id, repo["html_url"])
            else:
                logger.info("Ingesting new project for user %s: %s", user_id, repo["html_url"])
                tasks.append(
                    ingestion_service.fetch_and_store_repo_files_metadata(user_id, repo, max_file_size=200_000)
                )
        if tasks:
            repo_ids = await asyncio.gather(*tasks)
            repo_ids = [repo_id for repo_id in repo_ids if repo_id]
            if repo_ids:
                processing_service = RepositoryProcessingService(access_token)
                pool = await get_db_pool()
                async with pool.acquire() as conn:
                    await processing_service.process_repositories(user_id, repo_ids, conn)
    except Exception as e:
        logger.error("Error during repo metadata ingestion: %s", e)


async def get_current_user_from_token(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    token = authorization.split(" ")[1]
    payload = _verify_supabase_token(token)
    supabase_uid = payload.get("sub")
    if not supabase_uid:
        raise HTTPException(status_code=401, detail="Supabase user id missing.")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT uid FROM users WHERE supabase_uid = $1",
            supabase_uid,
        )
    if not row:
        raise HTTPException(status_code=401, detail="User not onboarded. Call /auth/supabase/session.")
    return {"uid": row["uid"], "supabase_uid": supabase_uid}


@router.post("/session")
async def upsert_supabase_session(
    payload: SupabaseSessionPayload,
    authorization: str = Header(...),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    token = authorization.split(" ")[1]
    decoded = _verify_supabase_token(token)
    supabase_uid = decoded.get("sub")
    if not supabase_uid:
        raise HTTPException(status_code=401, detail="Supabase user id missing.")
    if not payload.provider_token:
        raise HTTPException(status_code=400, detail="provider_token is required.")

    username = await _get_github_username(payload.provider_token)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (username, access_code, supabase_uid)
            VALUES ($1, $2, $3)
            ON CONFLICT (supabase_uid) DO UPDATE SET
                username = EXCLUDED.username,
                access_code = EXCLUDED.access_code
            """,
            username,
            payload.provider_token,
            supabase_uid,
        )
        row = await conn.fetchrow(
            "SELECT uid FROM users WHERE supabase_uid = $1",
            supabase_uid,
        )

    asyncio.create_task(_fetch_and_store_all_repos(row["uid"], payload.provider_token))

    return {"user_id": row["uid"], "username": username}
