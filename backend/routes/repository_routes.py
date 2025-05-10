from fastapi import APIRouter, Depends, HTTPException
from typing import List
from data_ingestion.github_ingestion import GitHubIngestionService
from auth.jwt import get_current_user_from_token
from db import get_db_pool

router = APIRouter()

@router.post("/repositories/ingest")
async def ingest_repositories(authorization: str = Depends(get_current_user_from_token)):
    """Ingest all repositories for the authenticated user."""
    user_id = authorization["uid"]
    
    # Get user's access token
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT access_code FROM users WHERE uid = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    
    # Initialize GitHub ingestion service
    ingestion_service = GitHubIngestionService(user["access_code"])
    
    # Fetch user's repositories
    try:
        repos = await ingestion_service.fetch_user_repositories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch repositories: {str(e)}")
    
    # Process each repository
    results = []
    for repo in repos:
        try:
            await ingestion_service.process_repository(user_id, repo["full_name"])
            results.append({
                "name": repo["name"],
                "status": "success"
            })
        except Exception as e:
            results.append({
                "name": repo["name"],
                "status": "error",
                "error": str(e)
            })
    
    return {
        "message": "Repository ingestion completed",
        "results": results
    }

@router.get("/repositories")
async def get_user_repositories(authorization: str = Depends(get_current_user_from_token)):
    """Get all repositories for the authenticated user."""
    user_id = authorization["uid"]
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        repos = await conn.fetch("""
            SELECT p.project_id, p.github_url, p.chunk_id,
                   COUNT(rf.id) as file_count,
                   COUNT(fc.id) as chunk_count
            FROM projects p
            LEFT JOIN repository_files rf ON p.project_id = rf.project_id
            LEFT JOIN file_chunks fc ON rf.id = fc.file_id
            WHERE p.user_id = $1
            GROUP BY p.project_id, p.github_url, p.chunk_id
            ORDER BY p.project_id DESC
        """, user_id)
        
        return [dict(repo) for repo in repos] 