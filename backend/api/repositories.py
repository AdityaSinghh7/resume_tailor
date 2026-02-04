from fastapi import APIRouter, Depends, HTTPException, Body
from auth.supabase_auth import get_current_user_from_token
from db import get_db_pool
from pydantic import BaseModel
from data_ingestion.github_ingestion import GitHubIngestionService

router = APIRouter()

class StarRambleUpdate(BaseModel):
    star_ramble: str

@router.get("/ingested_files")
async def get_ingested_files(authorization: dict = Depends(get_current_user_from_token)):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.project_id,
                   p.github_url,
                   p.full_name,
                   p.selected,
                   (p.summary_embedding_vector IS NOT NULL) AS embeddings_ready,
                   rf.id AS file_id,
                   rf.file_path,
                   rf.language,
                   rf.path_bucket
            FROM projects p
            LEFT JOIN repository_files rf ON p.project_id = rf.project_id
            WHERE p.user_id = $1
            ORDER BY p.project_id DESC, rf.file_path ASC
            """,
            user_id,
        )

    grouped = {}
    for row in rows:
        project_id = row["project_id"]
        repo = grouped.get(project_id)
        if repo is None:
            repo = {
                "project_id": project_id,
                "github_url": row["github_url"],
                "full_name": row["full_name"],
                "selected": row["selected"],
                "embeddings_ready": row["embeddings_ready"],
                "file_count": 0,
                "files": [],
            }
            grouped[project_id] = repo
        if row["file_id"] is not None:
            repo["file_count"] += 1
            repo["files"].append(
                {
                    "id": row["file_id"],
                    "file_path": row["file_path"],
                    "language": row["language"],
                    "path_bucket": row["path_bucket"],
                }
            )

    return list(grouped.values())


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
