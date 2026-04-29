import os

from dotenv import load_dotenv

load_dotenv()


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://paradiddle-earth:11434")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

if not POSTGRES_DSN:
    raise ValueError("POSTGRES_DSN environment variable is not set")
