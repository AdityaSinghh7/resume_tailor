from typing import List, Optional
import logging
import asyncio
import hashlib
import os
from db import get_db_pool
from data_ingestion.github_ingestion import GitHubIngestionService, TEXT_FILE_EXTENSIONS
from .chunking import chunk_code, chunk_text, embed_texts, generate_project_summary
import numpy as np

class RepositoryProcessingService:
    """
    Service for processing repositories: chunking, embedding, and storing in DB.
    """
    def __init__(self, access_token: str):
        self.ingestion_service = GitHubIngestionService(access_token)
        self.max_fetch_concurrency = int(os.getenv("GITHUB_FETCH_CONCURRENCY", "8"))
        self.max_file_summary_chars = int(os.getenv("FILE_SUMMARY_MAX_CHARS", "4000"))
        self.max_file_summary_chunks = int(os.getenv("FILE_SUMMARY_MAX_CHUNKS", "8"))

    async def process_repositories(self, user_id: int, repo_ids: List[int], conn) -> None:
        projects = await conn.fetch(
            "SELECT project_id, github_url FROM projects WHERE user_id = $1 AND project_id = ANY($2::int[])",
            user_id, repo_ids
        )
        for project in projects:
            project_id = project["project_id"]
            content_updated = False
            # Process STAR ramble
            ramble_row = await conn.fetchrow(
                "SELECT star_ramble FROM projects WHERE project_id = $1", project_id
            )
            if ramble_row and ramble_row["star_ramble"]:
                ramble_content = ramble_row["star_ramble"]
                ramble_chunks = chunk_text(ramble_content)
                ramble_embeddings = embed_texts(ramble_chunks)
                for idx, (chunk, embedding) in enumerate(zip(ramble_chunks, ramble_embeddings)):
                    await conn.execute(
                        """
                        INSERT INTO file_chunks (file_id, project_id, chunk_index, content, embedding_vector, chunk_type)
                        VALUES (NULL, $1, $2, $3, $4, $5)
                        ON CONFLICT (project_id) WHERE chunk_type = 'ramble' DO UPDATE SET content = EXCLUDED.content, embedding_vector = EXCLUDED.embedding_vector, chunk_type = EXCLUDED.chunk_type
                        """,
                        project_id, idx, chunk, str(embedding.tolist()), 'ramble'
                    )
                content_updated = True
            # Process files
            files = await conn.fetch(
                "SELECT id, file_path, file_type, content_hash, tech_tags FROM repository_files WHERE project_id = $1",
                project_id
            )
            chunk_counts = await conn.fetch(
                "SELECT file_id, COUNT(*) AS chunk_count FROM file_chunks WHERE project_id = $1 GROUP BY file_id",
                project_id
            )
            chunk_count_map = {row["file_id"]: row["chunk_count"] for row in chunk_counts}

            semaphore = asyncio.Semaphore(self.max_fetch_concurrency)

            async def fetch_with_semaphore(file_row):
                async with semaphore:
                    content = await self._fetch_file_content(file_row["file_path"])
                return file_row, content

            fetch_tasks = [fetch_with_semaphore(file_row) for file_row in files]
            fetch_results = await asyncio.gather(*fetch_tasks)

            for file_row, content in fetch_results:
                if not content:
                    continue
                file_id = file_row["id"]
                abs_file_path = file_row["file_path"]
                file_type = file_row["file_type"]
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                existing_hash = file_row["content_hash"]
                if existing_hash == content_hash and chunk_count_map.get(file_id, 0) > 0:
                    continue
                await conn.execute(
                    "UPDATE repository_files SET content_hash = $1 WHERE id = $2",
                    content_hash, file_id
                )
                ext = f".{file_type.lower()}" if file_type else ""
                content_type = "code" if ext in TEXT_FILE_EXTENSIONS else "informational"
                if content_type == "code":
                    chunks = chunk_code(content, file_type)
                else:
                    chunks = chunk_text(content)
                embeddings = embed_texts(chunks)
                for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    await conn.execute(
                        """
                        INSERT INTO file_chunks (file_id, project_id, chunk_index, content, embedding_vector, chunk_type)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (file_id, chunk_index) DO UPDATE SET content = EXCLUDED.content, embedding_vector = EXCLUDED.embedding_vector, chunk_type = EXCLUDED.chunk_type
                        """,
                        file_id, project_id, idx, chunk, str(embedding.tolist()), content_type
                    )
                file_summary = self._build_file_summary(chunks)
                if file_summary:
                    file_embedding = embed_texts([file_summary])[0]
                    existing_tags = file_row["tech_tags"] or []
                    merged_tags = self._merge_tags(existing_tags, self._extract_tech_tags(file_summary, abs_file_path, file_type))
                    await conn.execute(
                        """
                        UPDATE repository_files
                        SET summary = $1,
                            summary_embedding_vector = $2,
                            tech_tags = $3
                        WHERE id = $4
                        """,
                        file_summary, str(file_embedding.tolist()), merged_tags, file_id
                    )
                content_updated = True
            # After processing all files and rambles, generate and store project summary and embedding
            # Gather all chunk contents for this project
            if content_updated:
                file_summary_rows = await conn.fetch(
                    "SELECT summary FROM repository_files WHERE project_id = $1 AND summary IS NOT NULL",
                    project_id
                )
                all_contents = [row["summary"] for row in file_summary_rows if row["summary"]]
                if not all_contents:
                    chunk_rows = await conn.fetch(
                        "SELECT content FROM file_chunks WHERE project_id = $1 ORDER BY chunk_index ASC",
                        project_id
                    )
                    all_contents = [row["content"] for row in chunk_rows if row["content"]]
                if all_contents:
                    summary = generate_project_summary(all_contents)
                    summary_embedding = embed_texts([summary])[0]
                    await conn.execute(
                        """
                        UPDATE projects SET summary = $1, summary_embedding_vector = $2 WHERE project_id = $3
                        """,
                        summary, str(summary_embedding.tolist()), project_id
                    )

    async def _fetch_file_content(self, abs_file_path: str) -> Optional[str]:
        try:
            repo_full_name, file_path = abs_file_path.split('/', 2)[0:2], abs_file_path.split('/', 2)[2]
            repo_full_name = '/'.join(repo_full_name)
            contents = await self.ingestion_service.fetch_repository_contents(repo_full_name, file_path)
            import base64
            if isinstance(contents, dict) and contents.get("type") == "file":
                return base64.b64decode(contents["content"]).decode("utf-8", errors="replace")
        except Exception as e:
            logging.error(f"Error fetching content for {abs_file_path}: {e}")
        return None 

    def _build_file_summary(self, chunks: List[str]) -> str:
        if not chunks:
            return ""
        selected = chunks[: self.max_file_summary_chunks]
        summary = "\n".join(selected)
        if len(summary) > self.max_file_summary_chars:
            summary = summary[: self.max_file_summary_chars]
        return summary

    def _extract_tech_tags(self, text: str, file_path: str, file_type: Optional[str]) -> List[str]:
        lowered = f"{file_path}\n{text}".lower()
        tag_map = {
            "next.js": "nextjs",
            "nextjs": "nextjs",
            "react": "react",
            "vue": "vue",
            "svelte": "svelte",
            "angular": "angular",
            "node": "node",
            "express": "express",
            "fastapi": "fastapi",
            "django": "django",
            "flask": "flask",
            "graphql": "graphql",
            "rest": "rest",
            "postgres": "postgres",
            "postgresql": "postgres",
            "mysql": "mysql",
            "sqlite": "sqlite",
            "mongodb": "mongodb",
            "redis": "redis",
            "supabase": "supabase",
            "docker": "docker",
            "kubernetes": "kubernetes",
            "k8s": "kubernetes",
            "terraform": "terraform",
            "aws": "aws",
            "gcp": "gcp",
            "azure": "azure",
            "openai": "openai",
            "langchain": "langchain",
            "pytorch": "pytorch",
            "tensorflow": "tensorflow",
            "numpy": "numpy",
            "pandas": "pandas",
            "tailwind": "tailwind",
            "chakra": "chakra",
            "mui": "mui",
            "prisma": "prisma",
            "drizzle": "drizzle",
            "vite": "vite",
            "webpack": "webpack",
            "turborepo": "turborepo",
            "bun": "bun",
            "deno": "deno",
            "typescript": "typescript",
            "javascript": "javascript",
            "python": "python",
            "go": "go",
            "rust": "rust",
            "java": "java",
            "kotlin": "kotlin",
            "swift": "swift",
            "dart": "dart",
            "c++": "cpp",
            "cpp": "cpp",
            "c#": "csharp",
            "csharp": "csharp",
        }
        found = set()
        for needle, tag in tag_map.items():
            if needle in lowered:
                found.add(tag)
        if file_type:
            found.add(file_type.lower())
        return sorted(found)

    def _merge_tags(self, existing: List[str], new: List[str]) -> List[str]:
        merged = set(existing or [])
        merged.update(new or [])
        return sorted(merged)
