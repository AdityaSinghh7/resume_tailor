import httpx
import asyncio
from typing import List, Dict, Any
import hashlib
from datetime import datetime
from db import get_db_pool
import logging
from fastapi import HTTPException

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

class GitHubIngestionService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = "https://api.github.com"

    def is_text_file(self, file_path: str) -> bool:
        """Check if a file is likely to be a text file based on its extension."""
        return any(file_path.lower().endswith(ext) for ext in TEXT_FILE_EXTENSIONS)

    async def fetch_user_repositories(self) -> List[Dict[str, Any]]:
        """Fetch all repositories for the authenticated user."""
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
        """Fetch contents of a repository directory."""
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

    async def fetch_file_content(self, repo_name: str, file_path: str) -> str:
        """Fetch content of a specific file."""
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching content for {repo_name}/{file_path}")
            response = await client.get(
                f"{self.base_url}/repos/{repo_name}/contents/{file_path}",
                headers=self.headers
            )
            response.raise_for_status()
            content = response.json()
            import base64
            decoded_content = base64.b64decode(content["content"]).decode("utf-8")
            logger.info(f"Successfully fetched content for {repo_name}/{file_path} ({len(decoded_content)} bytes)")
            return decoded_content

    def calculate_content_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def store_project(self, user_id: int, repo_data: Dict[str, Any]) -> int:
        """Store project metadata in the database."""
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                # Generate a unique chunk_id for the project
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

    async def store_file(self, project_id: int, file_path: str, content: str) -> int:
        """Store file content in the database."""
        try:
            content_hash = self.calculate_content_hash(content)
            file_type = file_path.split(".")[-1] if "." in file_path else ""

            pool = await get_db_pool()
            async with pool.acquire() as conn:
                logger.info(f"Storing file: {file_path} for project {project_id}")
                file_id = await conn.fetchval("""
                    INSERT INTO repository_files (
                        project_id, file_path, file_type, content_hash
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (project_id, file_path) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """,
                    project_id,
                    file_path,
                    file_type,
                    content_hash
                )
                logger.info(f"Successfully stored file with ID: {file_id}")
                return file_id
        except Exception as e:
            logger.error(f"Error storing file {file_path}: {str(e)}")
            raise

    async def store_file_chunks(self, file_id: int, content: str, chunk_size: int = 1000) -> None:
        """Split content into chunks and store them."""
        try:
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
            
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                logger.info(f"Storing {len(chunks)} chunks for file {file_id}")
                for i, chunk in enumerate(chunks):
                    await conn.execute("""
                        INSERT INTO file_chunks (
                            file_id, chunk_index, content
                        ) VALUES ($1, $2, $3)
                        ON CONFLICT (file_id, chunk_index) DO UPDATE
                        SET content = EXCLUDED.content,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                        file_id,
                        i,
                        chunk
                    )
                logger.info(f"Successfully stored all chunks for file {file_id}")
        except Exception as e:
            logger.error(f"Error storing chunks for file {file_id}: {str(e)}")
            raise

    async def process_repository(self, user_id: int, repo_name: str) -> None:
        """Process a single repository: fetch and store all its contents."""
        try:
            # First, get repository metadata
            async with httpx.AsyncClient() as client:
                logger.info(f"Fetching metadata for repository: {repo_name}")
                response = await client.get(
                    f"{self.base_url}/repos/{repo_name}",
                    headers=self.headers
                )
                if response.status_code != 200:
                    logger.error(f"Failed to fetch repository metadata for {repo_name}. Status: {response.status_code}, Response: {response.text}")
                    raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch repository metadata: {response.text}")
                
                repo_data = response.json()
                logger.info(f"Successfully fetched metadata for {repo_name}. Visibility: {repo_data.get('visibility', 'unknown')}")

            logger.info(f"Processing repository: {repo_name}")
            # Store project metadata
            project_id = await self.store_project(user_id, repo_data)

            # Process repository contents recursively
            try:
                await self._process_directory(repo_name, project_id)
                logger.info(f"Successfully processed repository: {repo_name}")
            except Exception as e:
                logger.error(f"Error processing directory for {repo_name}: {str(e)}")
                raise

        except Exception as e:
            logger.error(f"Error processing repository {repo_name}: {str(e)}")
            raise

    async def _process_directory(self, repo_name: str, project_id: int, path: str = "") -> None:
        """Recursively process a directory in the repository."""
        try:
            logger.info(f"Fetching contents for {repo_name}/{path}")
            contents = await self.fetch_repository_contents(repo_name, path)
            
            for item in contents:
                if item["type"] == "file":
                    if self.is_text_file(item["path"]):
                        try:
                            logger.info(f"Processing file: {item['path']} in {repo_name}")
                            content = await self.fetch_file_content(repo_name, item["path"])
                            file_id = await self.store_file(project_id, item["path"], content)
                            await self.store_file_chunks(file_id, content)
                            logger.info(f"Successfully processed file: {item['path']}")
                        except Exception as e:
                            logger.error(f"Error processing file {item['path']} in {repo_name}: {str(e)}")
                elif item["type"] == "dir":
                    await self._process_directory(repo_name, project_id, item["path"])
        except Exception as e:
            logger.error(f"Error processing directory {path} in {repo_name}: {str(e)}")
            raise