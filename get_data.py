from __future__ import annotations

import argparse
import io
import importlib
import logging
import os
import random
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any
from dataclasses import dataclass
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

MASTERFILELIST_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist-translation.txt"
DEFAULT_DB_DSN = os.getenv("PG_DSN", "")
GDELT_V2_EXPORT_RE = re.compile(r"/gdeltv2/\d{14}\.translation\.export\.CSV\.zip$")

GDELT_EVENT_COLUMNS = [
    "globaleventid",
    "sqldate",
    "monthyear",
    "year",
    "fractiondate",
    "actor1code",
    "actor1name",
    "actor1countrycode",
    "actor1knowngroupcode",
    "actor1ethniccode",
    "actor1religion1code",
    "actor1religion2code",
    "actor1type1code",
    "actor1type2code",
    "actor1type3code",
    "actor2code",
    "actor2name",
    "actor2countrycode",
    "actor2knowngroupcode",
    "actor2ethniccode",
    "actor2religion1code",
    "actor2religion2code",
    "actor2type1code",
    "actor2type2code",
    "actor2type3code",
    "isrootevent",
    "eventcode",
    "eventbasecode",
    "eventrootcode",
    "quadclass",
    "goldsteinscale",
    "nummentions",
    "numsources",
    "numarticles",
    "avgtone",
    "actor1geo_type",
    "actor1geo_fullname",
    "actor1geo_countrycode",
    "actor1geo_adm1code",
    "actor1geo_adm2code",
    "actor1geo_lat",
    "actor1geo_long",
    "actor1geo_featureid",
    "actor2geo_type",
    "actor2geo_fullname",
    "actor2geo_countrycode",
    "actor2geo_adm1code",
    "actor2geo_adm2code",
    "actor2geo_lat",
    "actor2geo_long",
    "actor2geo_featureid",
    "actiongeo_type",
    "actiongeo_fullname",
    "actiongeo_countrycode",
    "actiongeo_adm1code",
    "actiongeo_adm2code",
    "actiongeo_lat",
    "actiongeo_long",
    "actiongeo_featureid",
    "dateadded",
    "sourceurl",
]

INT_COLUMNS = [
    "globaleventid",
    "sqldate",
    "monthyear",
    "year",
    "isrootevent",
    "quadclass",
    "nummentions",
    "numsources",
    "numarticles",
    "actor1geo_type",
    "actor2geo_type",
    "actiongeo_type",
    "dateadded",
]

FLOAT_COLUMNS = [
    "fractiondate",
    "goldsteinscale",
    "avgtone",
    "actor1geo_lat",
    "actor1geo_long",
    "actor2geo_lat",
    "actor2geo_long",
    "actiongeo_lat",
    "actiongeo_long",
]


@dataclass(frozen=True)
class GdeltFile:
    url: str

    @property
    def name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def init_db(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_files (
            file_name TEXT PRIMARY KEY,
            file_url TEXT NOT NULL,
            processed_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gdelt_brazil_events (
            id BIGSERIAL PRIMARY KEY,
            source_file TEXT NOT NULL,
            globaleventid BIGINT,
            sqldate BIGINT,
            monthyear INTEGER,
            year INTEGER,
            fractiondate DOUBLE PRECISION,
            actor1code TEXT,
            actor1name TEXT,
            actor1countrycode TEXT,
            actor1knowngroupcode TEXT,
            actor1ethniccode TEXT,
            actor1religion1code TEXT,
            actor1religion2code TEXT,
            actor1type1code TEXT,
            actor1type2code TEXT,
            actor1type3code TEXT,
            actor2code TEXT,
            actor2name TEXT,
            actor2countrycode TEXT,
            actor2knowngroupcode TEXT,
            actor2ethniccode TEXT,
            actor2religion1code TEXT,
            actor2religion2code TEXT,
            actor2type1code TEXT,
            actor2type2code TEXT,
            actor2type3code TEXT,
            isrootevent INTEGER,
            eventcode TEXT,
            eventbasecode TEXT,
            eventrootcode TEXT,
            quadclass INTEGER,
            goldsteinscale DOUBLE PRECISION,
            nummentions INTEGER,
            numsources INTEGER,
            numarticles INTEGER,
            avgtone DOUBLE PRECISION,
            actor1geo_type INTEGER,
            actor1geo_fullname TEXT,
            actor1geo_countrycode TEXT,
            actor1geo_adm1code TEXT,
            actor1geo_adm2code TEXT,
            actor1geo_lat DOUBLE PRECISION,
            actor1geo_long DOUBLE PRECISION,
            actor1geo_featureid TEXT,
            actor2geo_type INTEGER,
            actor2geo_fullname TEXT,
            actor2geo_countrycode TEXT,
            actor2geo_adm1code TEXT,
            actor2geo_adm2code TEXT,
            actor2geo_lat DOUBLE PRECISION,
            actor2geo_long DOUBLE PRECISION,
            actor2geo_featureid TEXT,
            actiongeo_type INTEGER,
            actiongeo_fullname TEXT,
            actiongeo_countrycode TEXT,
            actiongeo_adm1code TEXT,
            actiongeo_adm2code TEXT,
            actiongeo_lat DOUBLE PRECISION,
            actiongeo_long DOUBLE PRECISION,
            actiongeo_featureid TEXT,
            dateadded BIGINT,
            sourceurl TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            UNIQUE(source_file, globaleventid, sourceurl)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_gdelt_brazil_source_url
        ON gdelt_brazil_events(sourceurl)
        """
    )
    conn.commit()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_dns_resolution_error(exc: BaseException) -> bool:
    if isinstance(exc, socket.gaierror):
        return True

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.gaierror):
            return True
        text = str(reason or exc).lower()
    else:
        text = str(exc).lower()

    dns_markers = (
        "temporary failure in name resolution",
        "name or service not known",
        "nodename nor servname provided",
        "failed to resolve",
        "getaddrinfo failed",
    )
    return any(marker in text for marker in dns_markers)


def fetch_url_bytes_with_retry(
    url: str,
    timeout_seconds: int,
    user_agent: str,
    max_attempts: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> bytes:
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            # Retry only transient HTTP status codes.
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc

        if attempt >= max_attempts:
            break

        base_delay = retry_base_seconds * (2 ** (attempt - 1))
        delay = min(retry_max_seconds, base_delay) + random.uniform(0.0, 1.5)
        if last_exc and is_dns_resolution_error(last_exc):
            delay = max(delay, 5.0)

        logging.warning(
            "Request attempt %d/%d failed for %s (%s). Retrying in %.2fs.",
            attempt,
            max_attempts,
            url,
            last_exc,
            delay,
        )
        time.sleep(delay)

    if last_exc:
        raise last_exc
    raise RuntimeError(f"Request failed without exception for {url}")


def is_brazilian_source(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url.strip())
        host = (parsed.hostname or "").lower().strip(".")
        sites = {"globo.com", "g1.globo.com", "metropoles.com", "exame.com", "brasil247.com", "revistaoeste.com"}
        return host.endswith(".br") or any(host == site for site in sites)
    except Exception:
        return False


def fetch_masterfilelist(
    timeout_seconds: int = 60,
    max_attempts: int = 6,
    retry_base_seconds: float = 2.0,
    retry_max_seconds: float = 90.0,
) -> list[GdeltFile]:
    raw_payload = fetch_url_bytes_with_retry(
        url=MASTERFILELIST_URL,
        timeout_seconds=timeout_seconds,
        user_agent="tcc-gdelt-ingestor/1.0",
        max_attempts=max_attempts,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    )
    raw_text = raw_payload.decode("utf-8", errors="replace")

    files: list[GdeltFile] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            continue

        url = parts[2]
        if GDELT_V2_EXPORT_RE.search(url):
            files.append(GdeltFile(url=url))

    return files


def get_processed_files(conn) -> set[str]:
    rows = conn.execute("SELECT file_name FROM processed_files").fetchall()
    return {row[0] for row in rows}


def is_first_run(conn) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM processed_files").fetchone()
    return (row[0] if row else 0) == 0


def normalize_dataframe_types(df, pd_module):
    for col in INT_COLUMNS:
        df[col] = pd_module.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in FLOAT_COLUMNS:
        df[col] = pd_module.to_numeric(df[col], errors="coerce")

    return df.astype(object).where(pd_module.notna(df), None)


def get_existing_sourceurls(conn, sourceurls: list[str]) -> set[str]:
    if not sourceurls:
        return set()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sourceurl
            FROM gdelt_brazil_events
            WHERE sourceurl = ANY(%s)
            """,
            (sourceurls,),
        )
        return {row[0] for row in cur.fetchall()}


def process_file(
    conn,
    gdelt_file: GdeltFile,
    timeout_seconds: int = 120,
    max_attempts: int = 6,
    retry_base_seconds: float = 2.0,
    retry_max_seconds: float = 90.0,
) -> int:
    logging.info("Downloading %s", gdelt_file.name)
    zip_payload = fetch_url_bytes_with_retry(
        url=gdelt_file.url,
        timeout_seconds=timeout_seconds,
        user_agent="tcc-gdelt-ingestor/1.0",
        max_attempts=max_attempts,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    )

    inserted_count = 0
    now = utc_now_iso()
    pd: Any = importlib.import_module("pandas")

    with zipfile.ZipFile(io.BytesIO(zip_payload)) as zf:
        inner_name = zf.namelist()[0]
        with zf.open(inner_name, "r") as f:
            df = pd.read_csv(
                f,
                sep="\t",
                header=None,
                names=GDELT_EVENT_COLUMNS,
                dtype=str,
                keep_default_na=False,
                na_values=[],
            )

            if df.shape[1] != len(GDELT_EVENT_COLUMNS):
                raise ValueError(
                    f"Unexpected column count in {gdelt_file.name}: {df.shape[1]}"
                )

            df = df[df["sourceurl"].map(is_brazilian_source)]

            if not df.empty:
                df = df.drop_duplicates(subset=["sourceurl"])
                existing_sourceurls = get_existing_sourceurls(conn, df["sourceurl"].tolist())
                if existing_sourceurls:
                    before_count = len(df)
                    df = df[~df["sourceurl"].isin(existing_sourceurls)]
                    skipped = before_count - len(df)
                    if skipped > 0:
                        logging.info(
                            "Skipping %d rows from %s because sourceurl already exists.",
                            skipped,
                            gdelt_file.name,
                        )

            if not df.empty:
                df = normalize_dataframe_types(df, pd)
                df["source_file"] = gdelt_file.name
                df["ingested_at"] = now

                insert_columns = ["source_file", *GDELT_EVENT_COLUMNS, "ingested_at"]
                placeholders = ", ".join(["%s"] * len(insert_columns))
                insert_sql = f"""
                    INSERT INTO gdelt_brazil_events ({", ".join(insert_columns)})
                    VALUES ({placeholders})
                    ON CONFLICT (source_file, globaleventid, sourceurl) DO NOTHING
                """

                records = [
                    tuple(row) for row in df[insert_columns].itertuples(index=False, name=None)
                ]

                with conn.cursor() as cur:
                    cur.executemany(insert_sql, records)
                    inserted_count = max(cur.rowcount, 0)

    conn.execute(
        """
        INSERT INTO processed_files (file_name, file_url, processed_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (file_name)
        DO UPDATE SET
            file_url = EXCLUDED.file_url,
            processed_at = EXCLUDED.processed_at
        """,
        (gdelt_file.name, gdelt_file.url, now),
    )
    conn.commit()
    logging.info("Finished %s | inserted %d .br rows", gdelt_file.name, inserted_count)
    return inserted_count


def run_loop(
    db_dsn: str,
    poll_interval_seconds: int,
    download_cooldown_seconds: int,
    bootstrap_latest_files: int,
    request_max_attempts: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> None:
    psycopg = importlib.import_module("psycopg")
    with psycopg.connect(db_dsn) as conn:
        init_db(conn)
        first_run = is_first_run(conn)

        while True:
            try:
                all_files = fetch_masterfilelist(
                    max_attempts=request_max_attempts,
                    retry_base_seconds=retry_base_seconds,
                    retry_max_seconds=retry_max_seconds,
                )
                all_files.sort(key=lambda x: x.name, reverse=True)

                processed = get_processed_files(conn)
                pending = [f for f in all_files if f.name not in processed]

                if first_run and bootstrap_latest_files > 0 and pending:
                    pending = pending[-bootstrap_latest_files:]
                    logging.info(
                        "First run detected. Limiting bootstrap to %d latest files.",
                        len(pending),
                    )
                    first_run = False

                if not pending:
                    logging.info("No new files. Sleeping %ds.", poll_interval_seconds)
                    time.sleep(poll_interval_seconds)
                    continue

                logging.info("Found %d pending files.", len(pending))
                for i, gdelt_file in enumerate(pending, start=1):
                    logging.info("[%d/%d] Processing %s", i, len(pending), gdelt_file.name)
                    process_file(
                        conn,
                        gdelt_file,
                        max_attempts=request_max_attempts,
                        retry_base_seconds=retry_base_seconds,
                        retry_max_seconds=retry_max_seconds,
                    )
                    logging.info(
                        "Cooldown: sleeping %ds to avoid rate limits.",
                        download_cooldown_seconds,
                    )
                    time.sleep(download_cooldown_seconds)

            except KeyboardInterrupt:
                logging.info("Stopped by user.")
                break
            except (urllib.error.URLError, zipfile.BadZipFile, TimeoutError) as exc:
                logging.exception("Transient failure: %s", exc)
                logging.info("Sleeping %ds before retry.", poll_interval_seconds)
                time.sleep(poll_interval_seconds)
            except Exception as exc:
                logging.exception("Unexpected error: %s", exc)
                logging.info("Sleeping %ds before retry.", poll_interval_seconds)
                time.sleep(poll_interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously ingest GDELT 2.0 export files, keep only .br sources, "
            "and store them in PostgreSQL."
        )
    )
    parser.add_argument(
        "--db-dsn",
        default=DEFAULT_DB_DSN,
        help=(
            "PostgreSQL DSN, e.g. "
            "postgresql://user:password@host:5432/database "
            "(can also be set via PG_DSN env var)."
        ),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=300,
        help="Sleep time between checks when there are no new files (default: 300).",
    )
    parser.add_argument(
        "--download-cooldown-seconds",
        type=int,
        default=10,
        help="Cooldown after each downloaded file to reduce rate-limit risk (default: 10).",
    )
    parser.add_argument(
        "--bootstrap-latest-files",
        type=int,
        default=4,
        help=(
            "On a fresh database, only process the latest N files before entering "
            "normal continuous mode. Use 0 to backfill all available files."
        ),
    )
    parser.add_argument(
        "--request-max-attempts",
        type=int,
        default=6,
        help="Max attempts per HTTP request before giving up (default: 6).",
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=2.0,
        help="Base retry delay in seconds for exponential backoff (default: 2.0).",
    )
    parser.add_argument(
        "--retry-max-seconds",
        type=float,
        default=90.0,
        help="Maximum delay between retries in seconds (default: 90.0).",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    if not args.db_dsn:
        raise SystemExit("Missing PostgreSQL DSN. Pass --db-dsn or set PG_DSN.")
    BASE_COOLDOWN = 10
    run_loop(
        db_dsn=args.db_dsn,
        poll_interval_seconds=max(BASE_COOLDOWN, args.poll_interval_seconds),
        download_cooldown_seconds=max(BASE_COOLDOWN, args.download_cooldown_seconds),
        bootstrap_latest_files=max(0, args.bootstrap_latest_files),
        request_max_attempts=max(1, args.request_max_attempts),
        retry_base_seconds=max(0.5, args.retry_base_seconds),
        retry_max_seconds=max(1.0, args.retry_max_seconds),
    )


if __name__ == "__main__":
    main()
