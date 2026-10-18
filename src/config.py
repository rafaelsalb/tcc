import os

from dotenv import load_dotenv

load_dotenv()


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOTLIGHT_ENDPOINT = os.getenv("SPOTLIGHT_ENDPOINT", "http://localhost:2222/rest")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if not POSTGRES_DSN:
    raise ValueError("POSTGRES_DSN environment variable is not set")
