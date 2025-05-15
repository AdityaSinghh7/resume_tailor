import numpy as np

class RAGPipelineService:
    """
    Service for running Retrieval-Augmented Generation (RAG) pipeline for resume tailoring.
    """
    def __init__(self, db_pool, openai_client):
        self.db_pool = db_pool
        self.openai_client = openai_client

    async def generate_resume(self, user_id: int, job_description: str, n_projects: int, k_chunks: int = 3):
        # 1. Embed the job description
        job_desc_embedding = self._get_embedding(job_description)
        pool = self.db_pool
        async with pool.acquire() as conn:
            # 2. Retrieve top N project summaries by semantic similarity (cosine distance)
            rows = await conn.fetch(
                """
                SELECT project_id, title, summary, github_url, summary_embedding_vector
                FROM projects
                WHERE user_id = $1 AND summary_embedding_vector IS NOT NULL
                """,
                user_id
            )
            if not rows:
                return []
            # Compute cosine similarity
            scored = []
            for row in rows:
                vec = np.array(row["summary_embedding_vector"], dtype=np.float32)
                sim = self._cosine_similarity(job_desc_embedding, vec)
                scored.append((sim, row))
            # Sort by similarity, descending
            scored.sort(reverse=True, key=lambda x: x[0])
            top = scored[:n_projects]
            # For each project, get top K relevant chunks
            results = []
            for sim, row in top:
                project_id = row["project_id"]
                chunks = await self._get_top_chunks(conn, project_id, job_desc_embedding, k=k_chunks)
                results.append({
                    "project_id": project_id,
                    "title": row["title"],
                    "summary": row["summary"],
                    "github_url": row["github_url"],
                    "score": float(sim),
                    "top_chunks": chunks
                })
            return results

    async def _get_top_chunks(self, conn, project_id: int, query_embedding: np.ndarray, k: int = 3):
        # Fetch all chunks for the project with embeddings
        rows = await conn.fetch(
            """
            SELECT content, embedding_vector, chunk_type
            FROM file_chunks
            WHERE project_id = $1 AND embedding_vector IS NOT NULL
            """,
            project_id
        )
        if not rows:
            return []
        scored = []
        for row in rows:
            vec = np.array(row["embedding_vector"], dtype=np.float32)
            sim = self._cosine_similarity(query_embedding, vec)
            scored.append((sim, row))
        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:k]
        return [
            {
                "content": row["content"],
                "chunk_type": row["chunk_type"],
                "score": float(sim)
            }
            for sim, row in top
        ]

    def _get_embedding(self, text: str, model: str = "text-embedding-3-small"):
        text = text.replace("\n", " ")
        response = self.openai_client.embeddings.create(input=[text], model=model)
        return np.array(response.data[0].embedding, dtype=np.float32)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray):
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def generate_formatted_resume(self, user_id: int, job_description: str, n_projects: int):
        # 1. Embed the job description
        # 2. Retrieve top N project summaries by semantic similarity
        # 3. For each project, retrieve most relevant chunks
        # 4. Generate formatted resume entries
        # (Implementation to be filled in)
        pass 