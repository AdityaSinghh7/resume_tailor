from fastapi import APIRouter, Depends, HTTPException
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

@router.post("/process")
async def process_repository(
    request: ProcessRequest,
    authorization: dict = Depends(get_current_user_from_token)
):
    user_id = authorization["uid"]
    repo_ids = request.repo_ids
    if not repo_ids:
        raise HTTPException(status_code=400, detail="No repo_ids provided.")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Fetch current selected status for all requested repo_ids
        rows = await conn.fetch(
            "SELECT project_id, selected FROM projects WHERE user_id = $1 AND project_id = ANY($2::int[])",
            user_id, repo_ids
        )
        # Only process repos that are not already selected
        to_process = [row["project_id"] for row in rows if not row["selected"]]
        # Update selected status for all requested repos
        await conn.execute(
            """
            UPDATE projects SET selected = (project_id = ANY($1::int[])) WHERE user_id = $2
            """,
            repo_ids, user_id
        )
        if not to_process:
            return {"message": "All selected repositories are already processed. No action taken."}
        user_row = await conn.fetchrow("SELECT access_code FROM users WHERE uid = $1", user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")
        access_token = user_row["access_code"]
        service = RepositoryProcessingService(access_token)
        await service.process_repositories(user_id, to_process, conn)
    return {"message": f"Repository processing started for {len(to_process)} new repositories. Refactored pipeline used."}
