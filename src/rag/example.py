from llama_index.core import QueryBundle, VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
import asyncio
import os


OLLAMA_HOST = "http://paradiddle-earth:11434"

# Settings control global defaults
Settings.embed_model = OllamaEmbedding('qwen3-embedding:0.6b', base_url=OLLAMA_HOST)
Settings.llm = Ollama(
    model="llama3.1:8b",
    request_timeout=360.0,
    base_url=OLLAMA_HOST,
    # Manually set the context window to limit memory usage
    context_window=8000,
)

# Create a RAG tool using LlamaIndex
documents = SimpleDirectoryReader("data").load_data()
index = VectorStoreIndex.from_documents(
    documents,
    # we can optionally override the embed_model here
    # embed_model=Settings.embed_model,
)
query_engine = index.as_query_engine(
    # we can optionally override the llm here
    # llm=Settings.llm,
)


def multiply(a: float, b: float) -> float:
    """Useful for multiplying two numbers."""
    return a * b


async def search_documents(query: str | QueryBundle) -> str:
    """Useful for answering natural language questions about an personal essay written by Paul Graham."""
    response = await query_engine.aquery(query)
    return str(response)


# Now we can ask questions about the documents or do calculations
async def main():
    query = ["O que é o estreito de Ormuz?", "A diferença entre gripe e resfriado."]
    for q in query:
        result = await search_documents(q)
        print(result)


# Run the agent
if __name__ == "__main__":
    asyncio.run(main())
