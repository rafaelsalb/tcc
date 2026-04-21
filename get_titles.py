from __future__ import annotations

import argparse
import html
import http.client
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import psycopg
import trafilatura

load_dotenv()

DEFAULT_DB_DSN = os.getenv("PG_DSN", "")
USER_AGENT = "Mozilla/5.0 (compatible; tcc-title-backfill/1.0)"
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

TERMINAL_STATUSES = {
	"ok",
	"not_found",
	"gone",
	"login_required",
	"forbidden",
	"blocked",
}


def configure_logging() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(levelname)s] %(message)s",
	)


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def get_domain(url: str) -> str:
	try:
		return (urllib.parse.urlparse(url).hostname or "").lower().strip(".")
	except Exception:
		return ""


def ensure_title_columns(conn) -> None:
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title TEXT
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS article_content TEXT
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title_last_fetch_at TIMESTAMPTZ
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title_fetch_status TEXT
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title_fetch_error TEXT
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title_fetch_attempts INTEGER NOT NULL DEFAULT 0
		"""
	)
	conn.execute(
		"""
		ALTER TABLE gdelt_brazil_events
		ADD COLUMN IF NOT EXISTS title_next_retry_at TIMESTAMPTZ
		"""
	)
	conn.execute(
		"""
		CREATE INDEX IF NOT EXISTS idx_gdelt_brazil_events_title_pending
		ON gdelt_brazil_events (sourceurl)
		WHERE title IS NULL OR title = '' OR article_content IS NULL OR article_content = ''
		"""
	)
	conn.execute(
		"""
		CREATE INDEX IF NOT EXISTS idx_gdelt_brazil_events_title_next_retry
		ON gdelt_brazil_events (title_next_retry_at)
		"""
	)
	conn.commit()


def get_pending_urls(conn, limit: int | None, max_attempts: int) -> list[str]:
	sql = """
		SELECT sourceurl
		FROM gdelt_brazil_events
		WHERE sourceurl IS NOT NULL
		  AND sourceurl <> ''
		  AND (
			  title IS NULL OR title = ''
			  OR article_content IS NULL OR article_content = ''
		  )
		  AND COALESCE(title_fetch_attempts, 0) < %s
		  AND (title_next_retry_at IS NULL OR title_next_retry_at <= NOW())
		  AND COALESCE(title_fetch_status, '') NOT IN ('ok', 'not_found', 'gone', 'login_required', 'forbidden', 'blocked')
		GROUP BY sourceurl
		ORDER BY MIN(ingested_at) ASC
	"""
	params: tuple = (max_attempts,)
	if limit and limit > 0:
		sql += " LIMIT %s"
		params = (max_attempts, limit)

	with conn.cursor() as cur:
		cur.execute(sql, params)
		return [row[0] for row in cur.fetchall()]


def is_login_url(url: str) -> bool:
	value = (url or "").lower()
	login_markers = (
		"require_login",
		"/login",
		"signin",
		"credentials_cookie_auth",
		"acl_users",
	)
	return any(marker in value for marker in login_markers)


def decode_html(raw: bytes, response) -> str:
	charset = None
	try:
		charset = response.headers.get_content_charset()
	except Exception:
		charset = None
	encoding = charset or "utf-8"
	return raw.decode(encoding, errors="replace")


def fetch_html(url: str, timeout_seconds: int = 25) -> tuple[str | None, str, str | None, str | None]:
	candidates = [url]
	if url.startswith("http://"):
		candidates.append("https://" + url[len("http://"):])

	last_error = "unknown fetch failure"
	for candidate in dict.fromkeys(candidates):
		try:
			req = urllib.request.Request(candidate, headers={"User-Agent": USER_AGENT})
			with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
				status = getattr(resp, "status", 200)
				final_url = resp.geturl()

				if status != 200:
					if status == 404:
						return None, final_url, "not_found", "HTTP 404"
					if status == 410:
						return None, final_url, "gone", "HTTP 410"
					if status == 403:
						return None, final_url, "forbidden", "HTTP 403"
					if status == 429:
						return None, final_url, "rate_limited", "HTTP 429"
					if status >= 500:
						return None, final_url, "server_error", f"HTTP {status}"
					return None, final_url, "download_failed", f"HTTP {status}"

				if is_login_url(final_url):
					return None, final_url, "login_required", "redirected to login/auth page"

				try:
					raw = resp.read(2_000_000)
				except http.client.IncompleteRead as exc:
					raw = exc.partial or b""
					if raw:
						logging.debug(
							"IncompleteRead for %s (using %d partial bytes)",
							candidate,
							len(raw),
						)
					else:
						last_error = "incomplete_read_empty"
						continue
				if not raw:
					last_error = "empty response body"
					continue

				return decode_html(raw, resp), final_url, None, None

		except urllib.error.HTTPError as exc:
			status = exc.code
			if status == 404:
				return None, candidate, "not_found", "HTTP 404"
			if status == 410:
				return None, candidate, "gone", "HTTP 410"
			if status == 403:
				return None, candidate, "forbidden", "HTTP 403"
			if status == 429:
				return None, candidate, "rate_limited", "HTTP 429"
			if status >= 500:
				last_error = f"HTTP {status}"
				continue
			return None, candidate, "download_failed", f"HTTP {status}"
		except urllib.error.URLError as exc:
			last_error = str(exc)
			continue
		except TimeoutError:
			last_error = "timeout"
			continue

	return None, url, "download_failed", last_error


def extract_title_from_html(downloaded: str, url: str) -> tuple[str | None, str | None, str, str | None]:
	try:
		metadata = trafilatura.bare_extraction(
			downloaded,
			url=url,
			with_metadata=True,
			favor_precision=True,
		)
		title = ""
		article_content = ""
		if metadata:
			if isinstance(metadata, dict):
				title = (metadata.get("title") or "").strip()
				article_content = (metadata.get("text") or "").strip()
			else:
				title = (getattr(metadata, "title", "") or "").strip()
				article_content = (getattr(metadata, "text", "") or "").strip()
				if not title and hasattr(metadata, "as_dict"):
					as_dict = metadata.as_dict()
					if isinstance(as_dict, dict):
						title = (as_dict.get("title") or "").strip()
						if not article_content:
							article_content = (as_dict.get("text") or "").strip()

		if not title or not article_content:
			json_payload = trafilatura.extract(
				downloaded,
				url=url,
				output_format="json",
				with_metadata=True,
				favor_precision=True,
			)
			if json_payload:
				parsed = json.loads(json_payload)
				if isinstance(parsed, dict):
					if not title:
						title = (parsed.get("title") or "").strip()
					if not article_content:
						article_content = (parsed.get("text") or "").strip()

		if not title:
			match = TITLE_TAG_RE.search(downloaded)
			if match:
				title = html.unescape(match.group(1)).strip()
				title = re.sub(r"\s+", " ", title)

		if not title:
			return None, None, "no_title", "title not found in extraction"

		if not article_content:
			return title, None, "no_content", "article content not found in extraction"

		return title, article_content, "ok", None
	except Exception as exc:
		return None, None, "extract_failed", str(exc)


def extract_title(url: str) -> tuple[str | None, str | None, str, str | None]:
	downloaded, final_url, fetch_status, fetch_error = fetch_html(url)
	if fetch_status:
		return None, None, fetch_status, fetch_error
	if is_login_url(final_url):
		return None, None, "login_required", "redirected to login/auth page"
	return extract_title_from_html(downloaded or "", final_url)


def compute_next_retry_at(status: str, attempts: int) -> str | None:
	if status in TERMINAL_STATUSES:
		return None

	now = datetime.now(timezone.utc)
	if status == "rate_limited":
		delay = 30 * 60
	elif status in {"server_error", "download_failed"}:
		delay = min(6 * 60 * 60, 5 * 60 * max(1, attempts))
	elif status in {"extract_failed", "no_title", "no_content", "error"}:
		delay = min(24 * 60 * 60, 60 * 60 * max(1, attempts))
	else:
		delay = 2 * 60 * 60

	return (now + timedelta(seconds=delay)).isoformat()


def interleave_by_domain(urls: list[str]) -> list[str]:
	buckets: dict[str, deque[str]] = defaultdict(deque)
	for url in urls:
		domain = get_domain(url) or ""
		buckets[domain].append(url)

	ordered_domains = sorted(buckets.keys(), key=lambda d: len(buckets[d]), reverse=True)
	interleaved: list[str] = []
	while ordered_domains:
		next_round: list[str] = []
		for domain in ordered_domains:
			if buckets[domain]:
				interleaved.append(buckets[domain].popleft())
			if buckets[domain]:
				next_round.append(domain)
		ordered_domains = next_round

	return interleaved


def update_title_for_url(
	conn,
	sourceurl: str,
	title: str | None,
	article_content: str | None,
	status: str,
	error_message: str | None,
) -> int:
	now = utc_now_iso()
	next_retry_at = compute_next_retry_at(status, 1)
	with conn.cursor() as cur:
		cur.execute(
			"""
			UPDATE gdelt_brazil_events
			SET title = %s,
				article_content = %s,
				title_fetch_status = %s,
				title_fetch_error = %s,
				title_last_fetch_at = %s,
				title_fetch_attempts = COALESCE(title_fetch_attempts, 0) + 1,
				title_next_retry_at = %s::timestamptz
			WHERE sourceurl = %s
			""",
			(title, article_content, status, error_message, now, next_retry_at, sourceurl),
		)
		return cur.rowcount


def run(
	db_dsn: str,
	limit: int | None,
	base_cooldown_seconds: float,
	same_source_extra_cooldown_seconds: float,
	same_source_streak_threshold: int,
	heavy_source_threshold: int,
	heavy_source_extra_cooldown_seconds: float,
	max_attempts: int,
) -> None:
	with psycopg.connect(db_dsn) as conn:
		ensure_title_columns(conn)

		pending_urls = get_pending_urls(conn, limit, max_attempts)
		if not pending_urls:
			logging.info("No pending URLs without title/content.")
			return
		pending_urls = interleave_by_domain(pending_urls)

		domain_counts = Counter(get_domain(url) for url in pending_urls)
		logging.info("Found %d unique pending URLs.", len(pending_urls))

		processed = 0
		success = 0
		failed = 0

		prev_domain = ""
		same_domain_streak = 0

		for idx, url in enumerate(pending_urls, start=1):
			domain = get_domain(url)

			if domain and domain == prev_domain:
				same_domain_streak += 1
			else:
				same_domain_streak = 1
				prev_domain = domain

			title, article_content, status, error_message = extract_title(url)
			updated_rows = update_title_for_url(conn, url, title, article_content, status, error_message)
			conn.commit()

			processed += 1
			if status == "ok":
				success += 1
				logging.info(
					"[%d/%d] OK | domain=%s | rows=%d | title=%s | content_len=%d",
					idx,
					len(pending_urls),
					domain,
					updated_rows,
					title,
					len(article_content or ""),
				)
			else:
				failed += 1
				logging.warning(
					"[%d/%d] %s | domain=%s | rows=%d | url=%s | error=%s",
					idx,
					len(pending_urls),
					status,
					domain,
					updated_rows,
					url,
					error_message,
				)

			cooldown = base_cooldown_seconds

			if same_domain_streak >= same_source_streak_threshold:
				cooldown += same_source_extra_cooldown_seconds

			if domain and domain_counts[domain] >= heavy_source_threshold:
				cooldown += heavy_source_extra_cooldown_seconds

			if cooldown > 0:
				logging.info(
					"Cooldown %.2fs (domain=%s, streak=%d, pending_for_domain=%d)",
					cooldown,
					domain,
					same_domain_streak,
					domain_counts[domain],
				)
				time.sleep(cooldown)

		logging.info(
			"Done. processed=%d success=%d failed=%d",
			processed,
			success,
			failed,
		)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Backfill article titles in gdelt_brazil_events using trafilatura, "
			"with adaptive cooldown to reduce rate-limit risk for repeated sources."
		)
	)
	parser.add_argument(
		"--db-dsn",
		default=DEFAULT_DB_DSN,
		help=(
			"PostgreSQL DSN, e.g. postgresql://user:password@host:5432/database "
			"(or set PG_DSN env var)."
		),
	)
	parser.add_argument(
		"--limit",
		type=int,
		default=None,
		help="Max number of unique URLs to process in this run.",
	)
	parser.add_argument(
		"--base-cooldown-seconds",
		type=float,
		default=1.5,
		help="Base cooldown applied after each fetch.",
	)
	parser.add_argument(
		"--same-source-extra-cooldown-seconds",
		type=float,
		default=3.0,
		help="Extra cooldown when the same domain appears repeatedly.",
	)
	parser.add_argument(
		"--same-source-streak-threshold",
		type=int,
		default=3,
		help="Consecutive requests to same domain before extra cooldown starts.",
	)
	parser.add_argument(
		"--heavy-source-threshold",
		type=int,
		default=20,
		help="If a domain has at least this many pending URLs, apply extra cooldown.",
	)
	parser.add_argument(
		"--heavy-source-extra-cooldown-seconds",
		type=float,
		default=2.0,
		help="Extra cooldown for domains with large pending volume.",
	)
	parser.add_argument(
		"--max-attempts",
		type=int,
		default=4,
		help="Maximum fetch attempts per URL before it is skipped from future runs.",
	)
	return parser.parse_args()


def main() -> None:
	configure_logging()
	args = parse_args()

	if not args.db_dsn:
		raise SystemExit("Missing PostgreSQL DSN. Pass --db-dsn or set PG_DSN.")

	run(
		db_dsn=args.db_dsn,
		limit=args.limit,
		base_cooldown_seconds=max(0.0, args.base_cooldown_seconds),
		same_source_extra_cooldown_seconds=max(0.0, args.same_source_extra_cooldown_seconds),
		same_source_streak_threshold=max(1, args.same_source_streak_threshold),
		heavy_source_threshold=max(1, args.heavy_source_threshold),
		heavy_source_extra_cooldown_seconds=max(0.0, args.heavy_source_extra_cooldown_seconds),
		max_attempts=max(1, args.max_attempts),
	)


if __name__ == "__main__":
	main()
