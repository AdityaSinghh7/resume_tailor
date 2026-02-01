import httpx
from typing import List, Dict, Any, Optional
import hashlib
from datetime import datetime, timezone
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

LANGUAGE_BY_EXTENSION = {
    "py": "python",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "json": "json",
    "md": "markdown",
    "yml": "yaml",
    "yaml": "yaml",
    "xml": "xml",
    "sql": "sql",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "hpp": "cpp",
    "java": "java",
    "kt": "kotlin",
    "rs": "rust",
    "go": "go",
    "rb": "ruby",
    "php": "php",
    "swift": "swift",
    "dart": "dart",
    "vue": "vue",
    "svelte": "svelte",
    "astro": "astro",
}

PATH_BUCKETS = [
    ("src/", "src"),
    ("app/", "app"),
    ("apps/", "apps"),
    ("backend/", "backend"),
    ("frontend/", "frontend"),
    ("api/", "api"),
    ("services/", "services"),
    ("lib/", "lib"),
    ("packages/", "packages"),
    ("docs/", "docs"),
    ("test/", "test"),
    ("tests/", "test"),
    ("scripts/", "scripts"),
    ("config/", "config"),
    ("infra/", "infra"),
    (".github/", "github"),
]

def is_excluded_path(file_path: str) -> bool:
    return any(file_path.startswith(excl) for excl in EXCLUDED_DIRS)

def infer_language(file_path: str) -> str:
    if "." not in file_path:
        return ""
    ext = file_path.rsplit(".", 1)[-1].lower()
    return LANGUAGE_BY_EXTENSION.get(ext, ext)

def infer_path_bucket(file_path: str) -> str:
    lowered = file_path.lower()
    for prefix, bucket in PATH_BUCKETS:
        if lowered.startswith(prefix):
            return bucket
    return "other"

def extract_path_tags(file_path: str) -> List[str]:
    lowered = file_path.lower()
    tags = set()
    for prefix, bucket in PATH_BUCKETS:
        if lowered.startswith(prefix):
            tags.add(bucket)
    if "docker" in lowered:
        tags.add("docker")
    if "terraform" in lowered or "tf" in lowered:
        tags.add("terraform")
    if "k8s" in lowered or "kubernetes" in lowered:
        tags.add("kubernetes")
    if "next" in lowered:
        tags.add("nextjs")
    if "react" in lowered:
        tags.add("react")
    if "fastapi" in lowered:
        tags.add("fastapi")
    return sorted(tags)

def parse_github_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        logger.warning("Unable to parse GitHub timestamp: %s", value)
        return None

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
            logger.info(f"Successfully fetched contents for {repo_name}/{path}")
            return contents


    async def fetch_repository_tree(self, repo_full_name: str, ref: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching tree for {repo_full_name}@{ref}")
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}/git/trees/{ref}",
                headers=self.headers,
                params={"recursive": "1"},
            )
            response.raise_for_status()
            data = response.json()
            tree = data.get("tree", [])
            logger.info(f"Successfully fetched {len(tree)} tree items for {repo_full_name}@{ref}")
            return tree

    async def store_project(self, user_id: int, repo_data: Dict[str, Any]) -> int:
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                chunk_id = hashlib.sha256(f"{repo_data['id']}_{datetime.now().isoformat()}".encode()).hexdigest()
                logger.info(f"Storing project: {repo_data['html_url']} for user {user_id}")
                project_id = await conn.fetchval("""
                    INSERT INTO projects (
                        user_id, github_url, chunk_id, repo_id, full_name, default_branch, pushed_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, github_url) DO UPDATE
                    SET chunk_id = EXCLUDED.chunk_id,
                        repo_id = EXCLUDED.repo_id,
                        full_name = EXCLUDED.full_name,
                        default_branch = EXCLUDED.default_branch,
                        pushed_at = EXCLUDED.pushed_at
                    RETURNING project_id
                """,
                    user_id,
                    repo_data["html_url"],
                    chunk_id,
                    repo_data.get("id"),
                    repo_data.get("full_name"),
                    repo_data.get("default_branch"),
                    parse_github_timestamp(repo_data.get("pushed_at"))
                )
                logger.info(f"Successfully stored project with ID: {project_id}")
                return project_id
        except Exception as e:
            logger.error(f"Error storing project {repo_data['html_url']}: {str(e)}")
            raise

    async def store_files_metadata_bulk(self, rows: List[tuple]) -> None:
        if not rows:
            return
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO repository_files (
                    project_id, file_path, file_type, file_size, language, path_bucket, tech_tags
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (project_id, file_path) DO UPDATE
                SET file_type = EXCLUDED.file_type,
                    file_size = EXCLUDED.file_size,
                    language = EXCLUDED.language,
                    path_bucket = EXCLUDED.path_bucket,
                    tech_tags = EXCLUDED.tech_tags,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows
            )

    async def fetch_and_store_repo_files_metadata(self, user_id: int, repo_data: dict, max_file_size: int = 200_000) -> int:
        project_id = await self.store_project(user_id, repo_data)
        repo_full_name = repo_data["full_name"]
        ref = repo_data.get("default_branch", "main")
        tree = await self.fetch_repository_tree(repo_full_name, ref)
        rows = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            file_path = item.get("path", "")
            if not file_path or is_excluded_path(file_path):
                continue
            if not self.is_text_file(file_path):
                continue
            file_size = item.get("size", 0) or 0
            if file_size > max_file_size:
                continue
            file_type = file_path.split(".")[-1] if "." in file_path else ""
            language = infer_language(file_path)
            path_bucket = infer_path_bucket(file_path)
            tech_tags = extract_path_tags(file_path)
            abs_file_path = f"{repo_full_name}/{file_path}"
            rows.append((project_id, abs_file_path, file_type, file_size, language, path_bucket, tech_tags))
        await self.store_files_metadata_bulk(rows)
        return project_id

# Utility function to check if a project exists for a user
async def project_exists(user_id: int, github_url: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM projects WHERE user_id = $1 AND github_url = $2",
            user_id, github_url
        )
        return row is not None
