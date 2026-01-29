from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_db_pool
from auth.supabase_auth import get_current_user_from_token
from openai import OpenAI
from dotenv import load_dotenv
import os
from rag_pipeline.service import RAGPipelineService
import traceback

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
    print(f"[rag.py] Received /rag_resume request: job_description length={len(request.job_description)}, n_projects={request.n_projects}")
    user_id = authorization["uid"]
    pool = await get_db_pool()
    service = RAGPipelineService(pool, openai_client)
    try:
        result = await service.generate_formatted_resume(user_id, request.job_description, request.n_projects)
        print(f"[rag.py] Returning result with {len(result['entries'])} entries.")
        return result
    except Exception as e:
        print("[rag.py] ERROR:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) 
