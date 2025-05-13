-- 003_augmented_schema.sql

-- Enable pgvector extension (safe if already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding vector column to file_chunks for semantic search
ALTER TABLE file_chunks
ADD COLUMN IF NOT EXISTS embedding_vector vector(1536); -- Adjust dimension to match your embedding model

-- Add chunk_type column to file_chunks to distinguish between code, readme, ramble, etc.
ALTER TABLE file_chunks
ADD COLUMN IF NOT EXISTS chunk_type VARCHAR(32) DEFAULT 'code';

-- Add optional user-provided project title and STAR ramble to projects
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS title VARCHAR(255),
ADD COLUMN IF NOT EXISTS star_ramble TEXT;

-- Create index for efficient vector search (if using pgvector)
CREATE INDEX IF NOT EXISTS idx_file_chunks_embedding_vector ON file_chunks USING ivfflat (embedding_vector vector_cosine_ops);

-- Create index for chunk_type
CREATE INDEX IF NOT EXISTS idx_file_chunks_chunk_type ON file_chunks(chunk_type); 

-- Add 'selected' column to projects
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS selected BOOLEAN DEFAULT FALSE;

-- Add 'project_id' column to file_chunks, with foreign key constraint
ALTER TABLE file_chunks
ADD COLUMN IF NOT EXISTS project_id INTEGER,
ADD CONSTRAINT fk_file_chunks_project_id
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE;