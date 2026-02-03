from fastapi import APIRouter, Depends, HTTPException, Body
from auth.supabase_auth import get_current_user_from_token
from db import get_db_pool
from pydantic import BaseModel
from data_ingestion.github_ingestion import GitHubIngestionService

router = APIRouter()

class StarRambleUpdate(BaseModel):
    star_ramble: str


@router.get("/github_repos")
async def fetch_github_repositories(authorization: dict = Depends(get_current_user_from_token)):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT access_code FROM users WHERE uid = $1",
            user_id
        )
        if not row or not row["access_code"]:
            raise HTTPException(status_code=401, detail="GitHub access token missing.")
        access_token = row["access_code"]

    ingestion_service = GitHubIngestionService(access_token)
    repos = await ingestion_service.fetch_user_repositories()
    public_repos = [repo for repo in repos if not repo.get("private", False)]

    results = []
    for repo in public_repos:
        project_id = await ingestion_service.store_project(user_id, repo)
        results.append({
            "project_id": project_id,
            "github_url": repo.get("html_url"),
            "full_name": repo.get("full_name"),
            "default_branch": repo.get("default_branch"),
            "pushed_at": repo.get("pushed_at"),
            "selected": False,
            "embeddings_ready": False,
        })
    return results

@router.get("/repositories/{project_id}/star_ramble")
async def get_project_star_ramble(project_id: int, authorization: dict = Depends(get_current_user_from_token)):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT star_ramble FROM projects WHERE project_id = $1 AND user_id = $2",
            project_id, user_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found or not authorized")
        return {"star_ramble": row["star_ramble"] or ""}

@router.patch("/repositories/{project_id}/star_ramble")
async def update_project_star_ramble(
    project_id: int,
    payload: StarRambleUpdate = Body(...),
    authorization: dict = Depends(get_current_user_from_token)
):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE projects
            SET star_ramble = $1
            WHERE project_id = $2 AND user_id = $3
            """,
            payload.star_ramble, project_id, user_id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Project not found or not authorized")
        return {"message": "STAR ramble updated successfully."} 
