import numpy as np
import json
import ast
import re

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
                print(f"[service.py] Cosine similarity for project_id={row['project_id']}: {sim:.4f}")
            # Sort by similarity, descending
            scored.sort(reverse=True, key=lambda x: x[0])
            top = scored[:n_projects]
            # For each project, get top K relevant chunks
            results = []
            for sim, row in top:
                project_id = row["project_id"]
                chunks = await self._get_top_chunks(conn, project_id, job_desc_embedding, k=k_chunks)
                resume_entry = await self._generate_resume_entry_llm(
                    job_description=job_description,
                    project_title=row["title"],
                    github_url=row["github_url"],
                    summary=row["summary"],
                    top_chunks=chunks
                )
                results.append(resume_entry)
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
            vec_raw = row["embedding_vector"]
            if isinstance(vec_raw, str):
                vec = np.array(ast.literal_eval(vec_raw), dtype=np.float32)
            else:
                vec = np.array(vec_raw, dtype=np.float32)
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

    async def _generate_resume_entry_llm(self, job_description, project_title, github_url, summary, top_chunks):
        print(f"[service.py] Calling LLM for project_title={project_title}, github_url={github_url}")
        # Extract technologies/concepts from job description using LLM
        job_desc_techs = await self._extract_technologies(job_description)
        # Compose the system prompt
        system_prompt = (
            "You are an expert technical recruiter at a big tech company. Given a job description, a list of relevant technologies/concepts from the job description, and a project, "
            "parse and extract every minute and relevant technology, library, framework, API, tool, and architectural pattern used in the project, even if minor or only used in a small part. "
            "Generate a JSON object with the following fields: "
            "title (string), bullets (array of 3-4 concise bullet points), github_url (string), and technologies (array of strings). "
            "The technologies array should be ordered from most to least relevant to the job description. "
            "The first bullet point should be an overall description of the project. "
            "The subsequent bullet points should describe the most relevant details of the project in the following format: 'Accomplished [X] as measured by [Y], by doing [Z].' Use strong, resume-minded action verbs. "
            "IMPORTANT: Only use information that is explicitly present in the project summary, code, README, or provided chunks. "
            "Do NOT invent, infer, or assume any details that are not present in the project content, even if they are mentioned in the job description. "
            "If a detail is not present, omit it rather than guessing or making it up. "
            "The job description is provided only for alignment and relevance, not for inventing new facts. "
            "Bullets should be achievement-oriented and relevant to the job description, but strictly factual. "
            "Respond ONLY with a valid JSON object."
        )
        # Compose the user prompt
        user_prompt = (
            f"Job Description:\n{job_description}\n\n"
            f"Technologies/Concepts from Job Description: {', '.join(job_desc_techs)}\n\n"
            f"Project Title: {project_title}\n"
            f"GitHub URL: {github_url}\n"
            f"Project Summary: {summary}\n"
            f"Relevant Chunks:\n"
        )
        for i, chunk in enumerate(top_chunks):
            user_prompt += f"Chunk {i+1} ({chunk['chunk_type']}):\n{chunk['content']}\n\n"
        print(f"[service.py] User prompt size: {len(user_prompt)} characters | max_tokens: 1024 | temperature: 0.7")
        # Call the LLM
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        # Parse the JSON from the response
        content = response.choices[0].message.content
        # Clean up markdown code block if present
        if content.strip().startswith('```'):
            # Remove triple backticks and optional 'json' language tag
            content = content.strip().lstrip('`').lstrip('json').lstrip('\n').rstrip('`').strip()
            # Remove any trailing triple backticks
            if content.endswith('```'):
                content = content[:-3].strip()
        try:
            resume_entry = json.loads(content)
        except Exception as e:
            print(f"[service.py] ERROR parsing LLM response for project_title={project_title}: {e}")
            print(f"[service.py] LLM raw response: {content}")
            # fallback: return as plain text if parsing fails
            resume_entry = {"title": project_title, "bullets": [content], "github_url": github_url, "technologies": []}
        return resume_entry

    def _get_embedding(self, text: str, model: str = "text-embedding-3-small"):
        text = text.replace("\n", " ")
        response = self.openai_client.embeddings.create(input=[text], model=model)
        return np.array(response.data[0].embedding, dtype=np.float32)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray):
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def _extract_technologies(self, job_description: str):
        """
        Use the OpenAI LLM to extract a list of relevant technologies, frameworks, libraries, APIs, tools, and skills from the job description.
        Returns a Python list of strings.
        """
        system_prompt = (
            "You are an expert technical recruiter. Given a job description, extract and return ONLY a Python list of strings containing all relevant technologies, frameworks, libraries, APIs, tools, and technical skills mentioned or implied in the job description. "
            "Be exhaustive and do not include any explanation or extra text."
        )
        user_prompt = f"Job Description:\n{job_description}\n\nList all relevant technologies, frameworks, libraries, APIs, tools, and technical skills as a Python list of strings."
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=256
        )
        content = response.choices[0].message.content.strip()
        # Remove markdown code block formatting if present
        if content.startswith('```'):
            content = content.lstrip('`').lstrip('python').lstrip('json').lstrip('\n').rstrip('`').strip()
            if content.endswith('```'):
                content = content[:-3].strip()
        # Try to safely evaluate the Python list
        try:
            tech_list = ast.literal_eval(content)
            if isinstance(tech_list, list):
                print(f"[service.py] Extracted technologies from job description: {tech_list}")
                return [str(t).strip() for t in tech_list]
            else:
                print(f"[service.py] LLM extraction did not return a list. Raw: {content}")
                return []
        except Exception as e:
            print(f"[service.py] ERROR parsing LLM technology extraction: {e}")
            print(f"[service.py] LLM raw response: {content}")
            return []

    async def generate_formatted_resume(self, user_id: int, job_description: str, n_projects: int):
        print(f"[service.py] generate_formatted_resume called with user_id={user_id}, n_projects={n_projects}, job_description length={len(job_description)}")
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
            print(f"[service.py] Retrieved {len(rows)} projects from DB for user_id={user_id}")
            if not rows:
                print("[service.py] No projects found for user.")
                return {
                    "entries": []
                }
            # Compute cosine similarity
            scored = []
            for row in rows:
                vec_raw = row["summary_embedding_vector"]
                if isinstance(vec_raw, str):
                    vec = np.array(ast.literal_eval(vec_raw), dtype=np.float32)
                else:
                    vec = np.array(vec_raw, dtype=np.float32)
                sim = self._cosine_similarity(job_desc_embedding, vec)
                scored.append((sim, row))
                print(f"[service.py] Cosine similarity for project_id={row['project_id']}: {sim:.4f}")
            # Sort by similarity, descending
            scored.sort(reverse=True, key=lambda x: x[0])
            top = scored[:n_projects]
            print(f"[service.py] Top {len(top)} projects selected for resume generation.")
            # For each project, get top K relevant chunks and generate resume entry
            entries = []
            for sim, row in top:
                project_id = row["project_id"]
                print(f"[service.py] Generating entry for project_id={project_id}, sim={sim}")
                chunks = await self._get_top_chunks(conn, project_id, job_desc_embedding, k=3)
                resume_entry = await self._generate_resume_entry_llm(
                    job_description=job_description,
                    project_title=row["title"],
                    github_url=row["github_url"],
                    summary=row["summary"],
                    top_chunks=chunks
                )
                # Always set github_url from DB
                resume_entry["github_url"] = row["github_url"]
                # Add alignment_score to the entry
                resume_entry["alignment_score"] = sim
                entries.append(resume_entry)
            print(f"[service.py] Returning {len(entries)} resume entries.")
            return {
                "entries": entries
            } 