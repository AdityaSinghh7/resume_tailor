import httpx
import asyncio
from typing import List, Dict, Any
import hashlib
from datetime import datetime
from db import get_db_pool
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of text file extensions to process
TEXT_FILE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.scss', '.json',
    '.md', '.txt', '.yml', '.yaml', '.xml', '.sql', '.sh', '.bash', '.zsh',
    '.c', '.cpp', '.h', '.hpp', '.java', '.kt', '.rs', '.go', '.rb', '.php',
    '.swift', '.dart', '.ts', '.vue', '.svelte', '.astro'
}

EXCLUDED_DIRS = [
    'node_modules/', 'dist/', 'build/', 'target/', '.git/', '.venv/', '__pycache__/', '.mypy_cache/', '.pytest_cache/', '.next/', '.idea/', '.vscode/'
]

def is_excluded_path(file_path: str) -> bool:
    return any(file_path.startswith(excl) for excl in EXCLUDED_DIRS)

class GitHubIngestionService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = "https://api.github.com"

    def is_text_file(self, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in TEXT_FILE_EXTENSIONS)

    async def fetch_user_repositories(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            logger.info("Fetching user repositories from GitHub API")
            response = await client.get(
                f"{self.base_url}/user/repos",
                headers=self.headers,
                params={"per_page": 100}
            )
            response.raise_for_status()
            repos = response.json()
            logger.info(f"Successfully fetched {len(repos)} repositories")
            return repos

    async def fetch_repository_contents(self, repo_name: str, path: str = "") -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching contents for {repo_name}/{path}")
            response = await client.get(
                f"{self.base_url}/repos/{repo_name}/contents/{path}",
                headers=self.headers
            )
            response.raise_for_status()
            contents = response.json()
            logger.info(f"Successfully fetched {len(contents)} items from {repo_name}/{path}")
            return contents

    async def store_project(self, user_id: int, repo_data: Dict[str, Any]) -> int:
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                chunk_id = hashlib.sha256(f"{repo_data['id']}_{datetime.now().isoformat()}".encode()).hexdigest()
                logger.info(f"Storing project: {repo_data['html_url']} for user {user_id}")
                project_id = await conn.fetchval("""
                    INSERT INTO projects (
                        user_id, github_url, chunk_id
                    ) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, github_url) DO UPDATE
                    SET chunk_id = EXCLUDED.chunk_id
                    RETURNING project_id
                """,
                    user_id,
                    repo_data["html_url"],
                    chunk_id
                )
                logger.info(f"Successfully stored project with ID: {project_id}")
                return project_id
        except Exception as e:
            logger.error(f"Error storing project {repo_data['html_url']}: {str(e)}")
            raise

    async def store_file_metadata(self, project_id: int, abs_file_path: str, file_type: str) -> int:
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                logger.info(f"Storing file metadata: {abs_file_path} (type: {file_type}) for project {project_id}")
                file_id = await conn.fetchval("""
                    INSERT INTO repository_files (
                        project_id, file_path, file_type
                    ) VALUES ($1, $2, $3)
                    ON CONFLICT (project_id, file_path) DO UPDATE
                    SET file_type = EXCLUDED.file_type,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """,
                    project_id,
                    abs_file_path,
                    file_type
                )
                logger.info(f"Successfully stored file metadata with ID: {file_id}")
                return file_id
        except Exception as e:
            logger.error(f"Error storing file metadata {abs_file_path}: {str(e)}")
            raise

    async def fetch_and_store_repo_files_metadata(self, user_id: int, repo_data: dict, max_file_size: int = 200_000):
        project_id = await self.store_project(user_id, repo_data)
        repo_full_name = repo_data["full_name"]
        async def _process_dir(repo_full_name: str, project_id: int, path: str = ""):
            contents = await self.fetch_repository_contents(repo_full_name, path)
            for item in contents:
                file_path = item["path"]
                if is_excluded_path(file_path):
                    continue
                if item["type"] == "file":
                    file_type = file_path.split(".")[-1] if "." in file_path else ""
                    file_size = item.get("size", 0)
                    if self.is_text_file(file_path) and file_size <= max_file_size:
                        abs_file_path = f"{repo_full_name}/{file_path}"
                        await self.store_file_metadata(project_id, abs_file_path, file_type)
                elif item["type"] == "dir":
                    await _process_dir(repo_full_name, project_id, file_path)
        await _process_dir(repo_full_name, project_id)