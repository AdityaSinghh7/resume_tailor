from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from db import get_db_pool
from auth.github_oauth import get_current_user_from_token
from data_ingestion.github_ingestion import GitHubIngestionService, TEXT_FILE_EXTENSIONS
import logging
import base64
import os
from openai import OpenAI
from dotenv import load_dotenv 
import numpy as np
from tree_sitter import Parser
from .chunking import chunk_code, chunk_text, embed_texts
from .processing_service import RepositoryProcessingService
from tree_sitter_languages import get_language

router = APIRouter()

class ProcessRequest(BaseModel):
    repo_ids: List[int]

# Utility to split stored file_path into repo_full_name and file_path
# Example stored file_path: 'octocat/Hello-World/path/to/file.py'
def split_repo_and_path(abs_file_path: str):
    # repo_full_name is always the first two segments (owner/repo)
    parts = abs_file_path.split('/')
    repo_full_name = '/'.join(parts[:2])
    file_path = '/'.join(parts[2:])
    return repo_full_name, file_path

async def fetch_file_content_from_github(ingestion_service, abs_file_path: str):
    repo_full_name, file_path = split_repo_and_path(abs_file_path)
    try:
        contents = await ingestion_service.fetch_repository_contents(repo_full_name, file_path)
        if isinstance(contents, dict) and contents.get("type") == "file":
            content = base64.b64decode(contents["content"]).decode("utf-8", errors="replace")
            logging.info(f"Fetched content for {abs_file_path} (length: {len(content)})")
            return content
        else:
            logging.warning(f"No file content for {abs_file_path}")
            return None
    except Exception as e:
        logging.error(f"Error fetching content for {abs_file_path}: {e}")
        return None

INFORMATIONAL_EXTENSIONS = {'.md', '.txt', '.rst'}
INFORMATIONAL_FILENAMES = {'readme', 'README', 'README.md', 'readme.md'}

def classify_content_type(file_name: str, file_type: str, is_ramble: bool = False) -> str:
    if is_ramble:
        return "ramble"
    ext = f".{file_type.lower()}" if file_type else ""
    base = file_name.lower()
    if ext in TEXT_FILE_EXTENSIONS:
        return "code"
    if ext in INFORMATIONAL_EXTENSIONS or base in INFORMATIONAL_FILENAMES:
        return "informational"
    return "other"

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Prepare OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Prepare TreeSitter parser for Python and JavaScript (add more as needed)
TREE_SITTER_LANGUAGES = {}

# Map file extensions to tree-sitter language names (add more as grammars are available)
EXTENSION_LANGUAGE_MAP = {
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'jsx': 'javascript',
    'tsx': 'typescript',
    'java': 'java',
    'c': 'c',
    'cpp': 'cpp',
    'h': 'cpp',
    'hpp': 'cpp',
    'go': 'go',
    'rb': 'ruby',
    'php': 'php',
    'rs': 'rust',
    'swift': 'swift',
    'kt': 'kotlin',
    'dart': 'dart',
    'vue': 'vue',
    'svelte': 'svelte',
    # Add more as you add grammars
}

# Update the build_library call to include all grammars you want to support
# (You must have the grammar repos locally or installed via pip for this to work)
for ext, lang_name in EXTENSION_LANGUAGE_MAP.items():
    try:
        TREE_SITTER_LANGUAGES[ext] = get_language(lang_name)
    except Exception:
        pass

def chunk_code_with_treesitter(code: str, file_type: str):
    """Chunk code using TreeSitter by function/class for supported languages."""
    ext = file_type.lower()
    lang = TREE_SITTER_LANGUAGES.get(ext)
    if not lang:
        # fallback: chunk by 2000 chars
        return [code[i:i+2000] for i in range(0, len(code), 2000)]
    parser = Parser()
    parser.set_language(lang)
    tree = parser.parse(bytes(code, "utf8"))
    root = tree.root_node
    chunks = []
    # Language-specific node types
    NODE_TYPES = {
        'python': ["function_definition", "class_definition"],
        'javascript': ["function_declaration", "class_declaration"],
        'typescript': ["function_declaration", "class_declaration"],
        'java': ["method_declaration", "class_declaration"],
        'c': ["function_definition"],
        'cpp': ["function_definition", "class_specifier"],
        'go': ["function_declaration", "method_declaration"],
        'ruby': ["method", "class"],
        'php': ["function_definition", "class_declaration"],
        'rust': ["function_item", "struct_item", "enum_item", "impl_item"],
        'swift': ["function_declaration", "class_declaration", "struct_declaration"],
        'kotlin': ["function_declaration", "class_declaration"],
        'dart': ["function_declaration", "class_declaration"],
        'vue': [],  # treat as text
        'svelte': [],  # treat as text
    }
    lang_name = EXTENSION_LANGUAGE_MAP.get(ext, None)
    node_types = NODE_TYPES.get(lang_name, [])
    if node_types:
        for node in root.children:
            if node.type in node_types:
                chunk = code[node.start_byte:node.end_byte]
                chunks.append(chunk)
    if not chunks:
        # fallback: chunk by 2000 chars
        return [code[i:i+2000] for i in range(0, len(code), 2000)]
    return chunks

def chunk_text_generic(text: str, chunk_size: int = 2000):
    """Chunk text by paragraphs or fixed size."""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) > chunk_size:
            # further split
            for i in range(0, len(para), chunk_size):
                chunks.append(para[i:i+chunk_size])
        else:
            chunks.append(para)
    return chunks

def get_embedding(text: str, model: str = "text-embedding-3-small"):
    text = text.replace("\n", " ")
    response = openai_client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding

# In-memory status tracker (for demo; use Redis/DB for production)
PROCESS_STATUS = {}

@router.post("/process")
async def process_repository(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    authorization: dict = Depends(get_current_user_from_token)
):
    user_id = authorization["uid"]
    repo_ids = request.repo_ids
    if not repo_ids:
        raise HTTPException(status_code=400, detail="No repo_ids provided.")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Fetch all project IDs for the user
        all_rows = await conn.fetch(
            "SELECT project_id FROM projects WHERE user_id = $1",
            user_id
        )
        all_project_ids = [row["project_id"] for row in all_rows]
        # Set selected = true for those in repo_ids, false for the rest
        await conn.execute(
            """
            UPDATE projects SET selected = (project_id = ANY($1::int[])) WHERE user_id = $2
            """,
            repo_ids, user_id
        )
        # Set selected = false for all projects not in repo_ids
        unselected_ids = [pid for pid in all_project_ids if pid not in repo_ids]
        if unselected_ids:
            await conn.execute(
                "UPDATE projects SET selected = false WHERE user_id = $1 AND project_id = ANY($2::int[])",
                user_id, unselected_ids
            )
        # Fetch current selected status for all requested repo_ids
        rows = await conn.fetch(
            "SELECT project_id, selected, star_ramble FROM projects WHERE user_id = $1 AND project_id = ANY($2::int[])",
            user_id, repo_ids
        )
        to_process = []
        for row in rows:
            project_id = row["project_id"]
            is_selected = row["selected"]
            current_ramble = row["star_ramble"] or ""
            ramble_chunk_row = await conn.fetchrow(
                "SELECT content FROM file_chunks WHERE project_id = $1 AND chunk_type = 'ramble' ORDER BY id DESC LIMIT 1",
                project_id
            )
            last_processed_ramble = ramble_chunk_row["content"] if ramble_chunk_row else ""
            if (not is_selected) or (ramble_chunk_row is None) or (current_ramble.strip() != last_processed_ramble.strip()):
                to_process.append(project_id)
        if not to_process:
            PROCESS_STATUS[user_id] = {"status": "done", "message": "All selected repositories are already processed and rambles unchanged. No action taken."}
            return {"message": "All selected repositories are already processed and rambles unchanged. No action taken."}
        user_row = await conn.fetchrow("SELECT access_code FROM users WHERE uid = $1", user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")
        access_token = user_row["access_code"]
        service = RepositoryProcessingService(access_token)
        # Set status to processing
        PROCESS_STATUS[user_id] = {"status": "processing", "message": f"Processing {len(to_process)} repositories..."}
        # Schedule background task
        background_tasks.add_task(process_repositories_background, service, user_id, to_process)
    return {"message": f"Repository processing started for {len(to_process)} new repositories. Processing in background."}

async def process_repositories_background(service, user_id, to_process):
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await service.process_repositories(user_id, to_process, conn)
        PROCESS_STATUS[user_id] = {"status": "done", "message": "Processing complete."}
    except Exception as e:
        import traceback
        PROCESS_STATUS[user_id] = {"status": "error", "message": str(e), "trace": traceback.format_exc()}

@router.get("/process_status")
async def get_process_status(authorization: dict = Depends(get_current_user_from_token)):
    user_id = authorization["uid"]
    status = PROCESS_STATUS.get(user_id, {"status": "idle", "message": "No processing started."})
    return status
