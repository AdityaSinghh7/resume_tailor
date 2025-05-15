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
POSTGRES_USER = os.getenv("POSTGRES_USER", "resume_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "resume_password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "resume_tailor")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

_pool = None

async def get_db_pool():
    """Get database connection pool."""
    try:
        global _pool
        if _pool is None:
            logger.info(f"Connecting to database {POSTGRES_DB} at {POSTGRES_HOST}:{POSTGRES_PORT}")
            _pool = await asyncpg.create_pool(
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
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