from typing import List, Optional
import logging
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

    async def process_repositories(self, user_id: int, repo_ids: List[int], conn) -> None:
        projects = await conn.fetch(
            "SELECT project_id, github_url FROM projects WHERE user_id = $1 AND project_id = ANY($2::int[])",
            user_id, repo_ids
        )
        for project in projects:
            project_id = project["project_id"]
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
            # Process files
            files = await conn.fetch(
                "SELECT id, file_path, file_type FROM repository_files WHERE project_id = $1",
                project_id
            )
            for file in files:
                file_id = file["id"]
                abs_file_path = file["file_path"]
                file_type = file["file_type"]
                file_name = abs_file_path.split('/')[-1]
                # Classify content type
                ext = f".{file_type.lower()}" if file_type else ""
                if ext in TEXT_FILE_EXTENSIONS:
                    content_type = "code"
                else:
                    content_type = "informational"
                content = await self._fetch_file_content(abs_file_path)
                if not content:
                    continue
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
            # After processing all files and rambles, generate and store project summary and embedding
            # Gather all chunk contents for this project
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