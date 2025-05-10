-- Drop existing tables if they exist
DROP TABLE IF EXISTS file_chunks;
DROP TABLE IF EXISTS repository_files;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS users;

-- Create users table
CREATE TABLE users (
    uid SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    access_code VARCHAR(255) NOT NULL
);

-- Create projects table
CREATE TABLE projects (
    project_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    github_url VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(uid) ON DELETE CASCADE,
    UNIQUE(user_id, github_url)
);

-- Create repository files table
CREATE TABLE repository_files (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(50),
    content_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    UNIQUE(project_id, file_path)
);

-- Create file chunks table
CREATE TABLE file_chunks (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES repository_files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_id, chunk_index)
);

-- Create indexes for better query performance
CREATE INDEX idx_repository_files_project_id ON repository_files(project_id);
CREATE INDEX idx_file_chunks_file_id ON file_chunks(file_id);
CREATE INDEX idx_file_chunks_embedding_id ON file_chunks(embedding_id); 