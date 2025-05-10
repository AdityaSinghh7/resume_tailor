import os
import asyncpg
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database configuration
DB_USER = os.getenv("DB_USER", "resume_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "resume_password")
DB_NAME = os.getenv("DB_NAME", "resume_tailor")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

_pool = None

async def get_db_pool():
    """Get database connection pool."""
    try:
        global _pool
        if _pool is None:
            logger.info(f"Connecting to database {DB_NAME} at {DB_HOST}:{DB_PORT}")
            _pool = await asyncpg.create_pool(
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                host=DB_HOST,
                port=DB_PORT,
                min_size=1,
                max_size=10
            )
            logger.info("Successfully connected to database")
        return _pool
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        raise

async def close_db_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None