# from chonkie import TokenChunker
# import numpy as np
# from ollama import Client
# from sqlalchemy import MetaData, Table, create_engine, insert, select
# from sqlalchemy.orm import Session

# from db import engine

# metadata = MetaData()

# g1_articles = Table('g1_articles', metadata, autoload_with=engine)
# g1_chunks = Table('g1_chunks', metadata, autoload_with=engine)

# chunks = {}
# chunker = TokenChunker()
# client = Client(host="http://paradiddle-earth:11434")


# with Session(engine) as session:
#     stmt = select(g1_articles).where(g1_articles.c.text_content.is_not(None)).limit(5)
#     results = session.execute(stmt).fetchall()
#     for i in results:
#         chunks[i.url] = []
#         _chunks = chunker.chunk(i.text_content)
#         for c in _chunks:
#             chunks[i.url].append(c)

#     for url, c in chunks.items():
#         embeddings = []
#         for chunk in c:
#             embedding = client.embed('qwen3-embedding:0.6b', chunk.text, dimensions=768)
#             embeddings.append(np.array(embedding.embeddings[0]))
#         stmt = select(g1_articles.c.url).where(g1_articles.c.url == url)
#         article_id = session.execute(stmt).scalar_one()
#         for chunk, embedding in zip(c, embeddings):
#             stmt = insert(g1_chunks).values(
#                 chunk=chunk.text,
#                 article=article_id,
#                 embedding=embedding
#             )
#             session.execute(stmt)
#     session.commit()


#     # for i, row in enumerate(results):
#     #     with open(f"rag/article_{i}.txt", "w") as f:
#     #         f.write(f"{row.title}|{row.text_content}")


from app import App


def main():
    # query = "Pelo que o empresário é investigado?"
    # result = vectorizer.embed("qwen3-embedding:0.6b", [query], 768)
    # query_embeddings = result[0]
    # results = chunk_repo.query_chunks(query_embeddings)
    # best = results[0]
    # pprint(best)
    app = App()
    app.populate_chunks()


if __name__ == "__main__":
    main()
