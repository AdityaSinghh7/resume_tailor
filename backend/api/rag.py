from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_db_pool
from auth.github_oauth import get_current_user_from_token
from openai import OpenAI
from dotenv import load_dotenv
import os
from rag_pipeline.service import RAGPipelineService

router = APIRouter()

class RAGRequest(BaseModel):
    job_description: str
    n_projects: int

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

@router.post("/rag_resume")
async def rag_resume(
    request: RAGRequest,
    authorization: dict = Depends(get_current_user_from_token)
):
    user_id = authorization["uid"]
    pool = await get_db_pool()
    service = RAGPipelineService(pool, openai_client)
    try:
        resume_entries = await service.generate_resume(user_id, request.job_description, request.n_projects)
        return {"entries": resume_entries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 