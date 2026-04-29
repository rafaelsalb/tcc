FROM postgres:18

COPY ./enable_extensions.sql /docker-entrypoint-initdb.d/

# Install build dependencies, clone, and compile pgvector
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-server-dev-18 \
    && git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y build-essential git postgresql-server-dev-18 \
    && apt-get autoremove -y \
    && apt-get clean
