import asyncio
import os
from dotenv import load_dotenv
from db import get_db_pool

async def check_database():
    # Load environment variables
    load_dotenv()
    
    # Get database connection
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        # Check users table
        print("\n=== Users ===")
        users = await conn.fetch("SELECT * FROM users")
        for user in users:
            print(f"User ID: {user['uid']}")
            print(f"Username: {user['username']}")
            print(f"Access Code: {user['access_code'][:10]}...")  # Show only first 10 chars of access code
            print("---")

        # Check projects table
        print("\n=== Projects ===")
        projects = await conn.fetch("""
            SELECT p.*, u.username 
            FROM projects p 
            JOIN users u ON p.user_id = u.uid
        """)
        for project in projects:
            print(f"Project ID: {project['project_id']}")
            print(f"User: {project['username']}")
            print(f"GitHub URL: {project['github_url']}")
            print(f"Chunk ID: {project['chunk_id']}")
            print("---")

        # Check repository files
        print("\n=== Repository Files ===")
        files = await conn.fetch("""
            SELECT rf.*, p.github_url 
            FROM repository_files rf 
            JOIN projects p ON rf.project_id = p.project_id
            LIMIT 10
        """)
        for file in files:
            print(f"File ID: {file['id']}")
            print(f"Project: {file['github_url']}")
            print(f"File Path: {file['file_path']}")
            print(f"File Type: {file['file_type']}")
            print(f"Content Hash: {file['content_hash']}")
            print("---")

        # Check file chunks
        print("\n=== File Chunks ===")
        chunks = await conn.fetch("""
            SELECT fc.*, rf.file_path, p.github_url
            FROM file_chunks fc
            JOIN repository_files rf ON fc.file_id = rf.id
            JOIN projects p ON rf.project_id = p.project_id
            LIMIT 5
        """)
        for chunk in chunks:
            print(f"Chunk ID: {chunk['id']}")
            print(f"File: {chunk['file_path']}")
            print(f"Project: {chunk['github_url']}")
            print(f"Chunk Index: {chunk['chunk_index']}")
            print(f"Content Preview: {chunk['content'][:100]}...")  # Show first 100 chars
            print("---")

        # Get counts
        print("\n=== Database Statistics ===")
        stats = await conn.fetchrow("""
            SELECT 
                (SELECT COUNT(*) FROM users) as user_count,
                (SELECT COUNT(*) FROM projects) as project_count,
                (SELECT COUNT(*) FROM repository_files) as file_count,
                (SELECT COUNT(*) FROM file_chunks) as chunk_count
        """)
        print(f"Total Users: {stats['user_count']}")
        print(f"Total Projects: {stats['project_count']}")
        print(f"Total Files: {stats['file_count']}")
        print(f"Total Chunks: {stats['chunk_count']}")

if __name__ == "__main__":
    asyncio.run(check_database()) 