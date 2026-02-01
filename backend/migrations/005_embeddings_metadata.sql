-- 005_embeddings_metadata.sql

-- Repo-level metadata for faster diffing and search
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS repo_id BIGINT,
ADD COLUMN IF NOT EXISTS full_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS default_branch VARCHAR(255),
ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS tech_tags TEXT[];

-- File-level metadata + embeddings
ALTER TABLE repository_files
ADD COLUMN IF NOT EXISTS file_size INTEGER,
ADD COLUMN IF NOT EXISTS language VARCHAR(32),
ADD COLUMN IF NOT EXISTS path_bucket VARCHAR(64),
ADD COLUMN IF NOT EXISTS summary TEXT,
ADD COLUMN IF NOT EXISTS summary_embedding_vector vector(1536),
ADD COLUMN IF NOT EXISTS tech_tags TEXT[];

-- Vector indexes for fast similarity search
CREATE INDEX IF NOT EXISTS idx_projects_summary_embedding_vector
ON projects USING hnsw (summary_embedding_vector vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_repository_files_summary_embedding_vector
ON repository_files USING hnsw (summary_embedding_vector vector_cosine_ops);

-- Unique guard for repo ids (nullable-safe)
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_user_repo_id
ON projects (user_id, repo_id)
WHERE repo_id IS NOT NULL;

-- Helpful filters
CREATE INDEX IF NOT EXISTS idx_repository_files_project_id
ON repository_files (project_id);

CREATE INDEX IF NOT EXISTS idx_repository_files_language
ON repository_files (language);

CREATE INDEX IF NOT EXISTS idx_repository_files_path_bucket
ON repository_files (path_bucket);
