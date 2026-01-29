from fastapi import APIRouter, Depends, HTTPException, Body
from auth.supabase_auth import get_current_user_from_token
from db import get_db_pool
from pydantic import BaseModel

router = APIRouter()

class StarRambleUpdate(BaseModel):
    star_ramble: str

@router.get("/repositories")
async def get_user_repositories(authorization: dict = Depends(get_current_user_from_token)):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        repos = await conn.fetch(
            """
            SELECT p.project_id, p.github_url, p.chunk_id, p.selected,
                   COUNT(rf.id) as file_count,
                   COUNT(fc.id) as chunk_count
            FROM projects p
            LEFT JOIN repository_files rf ON p.project_id = rf.project_id
            LEFT JOIN file_chunks fc ON rf.id = fc.file_id
            WHERE p.user_id = $1
            GROUP BY p.project_id, p.github_url, p.chunk_id, p.selected
            ORDER BY p.project_id DESC
            """, user_id
        )
        return [dict(repo) for repo in repos]

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
