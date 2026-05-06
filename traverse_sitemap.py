from __future__ import annotations

import argparse
import gzip
import http.client
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
import psycopg
import trafilatura
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_DSN = os.getenv("PG_DSN", "")
DEFAULT_G1_SITEMAP_ROOT = "https://g1.globo.com/sitemap/g1"
DEFAULT_G1_INDEX_URL = f"{DEFAULT_G1_SITEMAP_ROOT}/sitemap.xml"

USER_AGENTS = [
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


@dataclass(frozen=True)
class SitemapFile:
	loc: str
	lastmod: str | None


@dataclass(frozen=True)
class SitemapArticle:
	loc: str
	lastmod: str | None
	image_loc: str | None


def configure_logging() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(levelname)s] %(message)s",
	)


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def parse_iso_date(value: str) -> date:
	try:
		return date.fromisoformat(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError(
			f"Invalid date '{value}'. Expected ISO format YYYY-MM-DD."
		) from exc


def get_domain(url: str) -> str:
	try:
		return (urllib.parse.urlparse(url).hostname or "").lower().strip(".")
	except Exception:
		return ""


def xml_local_name(tag: str) -> str:
	if "}" in tag:
		return tag.rsplit("}", 1)[-1]
	return tag


def randomized_sleep(base_seconds: float, jitter_seconds: float) -> None:
	delay = max(1.0, base_seconds + np.random.normal(0.0, 1.0))
	if delay > 0:
		logging.info("Cooldown %.2fs", delay)
		time.sleep(delay)


def fetch_bytes(
	url: str,
	timeout_seconds: int,
	max_attempts: int,
	base_cooldown_seconds: float,
	jitter_seconds: float,
	accept_header: str,
) -> tuple[bytes, str, int]:
	def decode_body(raw: bytes, content_encoding: str) -> bytes:
		encoding = (content_encoding or "").lower()
		if "gzip" in encoding:
			try:
				return gzip.decompress(raw)
			except Exception:
				pass
		if "deflate" in encoding:
			try:
				return zlib.decompress(raw)
			except Exception:
				try:
					return zlib.decompress(raw, -zlib.MAX_WBITS)
				except Exception:
					pass

		# Some endpoints return gzipped payloads without proper headers.
		if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
			try:
				return gzip.decompress(raw)
			except Exception:
				pass

		return raw

	last_error: str | None = None
	last_status = 0
	for attempt in range(1, max_attempts + 1):
		headers = {
			"User-Agent": random.choice(USER_AGENTS),
			"Accept": accept_header,
			"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
			"Accept-Encoding": "gzip, deflate",
			"Connection": "close",
		}
		req = urllib.request.Request(url, headers=headers)

		try:
			with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
				status = getattr(resp, "status", 200)
				final_url = resp.geturl()
				if status == 429:
					raise urllib.error.HTTPError(final_url, 429, "Too Many Requests", resp.headers, None)
				if status >= 500:
					raise urllib.error.HTTPError(final_url, status, f"HTTP {status}", resp.headers, None)
				raw_body = resp.read()
				decoded = decode_body(raw_body, resp.headers.get("Content-Encoding", ""))
				return decoded, final_url, status
		except http.client.IncompleteRead as exc:
			last_error = f"incomplete_read ({len(exc.partial or b'')} bytes partial)"
			if attempt >= max_attempts:
				break
			backoff = min(60.0, base_cooldown_seconds * (2 ** (attempt - 1)))
			logging.warning(
				"Chunked response interrupted for %s (%s). Retrying in %.2fs [%d/%d]",
				url,
				last_error,
				backoff,
				attempt,
				max_attempts,
			)
			randomized_sleep(backoff, jitter_seconds)
		except urllib.error.HTTPError as exc:
			last_error = f"HTTP {exc.code}"
			last_status = exc.code
			if exc.code in {403, 404}:
				raise
			if attempt >= max_attempts:
				break
			backoff = min(60.0, base_cooldown_seconds * (2 ** (attempt - 1)))
			logging.warning(
				"Request failed for %s (%s). Retrying in %.2fs [%d/%d]",
				url,
				last_error,
				backoff,
				attempt,
				max_attempts,
			)
			randomized_sleep(backoff, jitter_seconds)
		except (urllib.error.URLError, TimeoutError) as exc:
			last_error = str(exc)
			if attempt >= max_attempts:
				break
			backoff = min(60.0, base_cooldown_seconds * (2 ** (attempt - 1)))
			logging.warning(
				"Request failed for %s (%s). Retrying in %.2fs [%d/%d]",
				url,
				last_error,
				backoff,
				attempt,
				max_attempts,
			)
			randomized_sleep(backoff, jitter_seconds)

	raise RuntimeError(f"Failed to fetch {url}: {last_error or 'unknown error'} (status={last_status})")


def fetch_xml(
	url: str,
	timeout_seconds: int,
	max_attempts: int,
	base_cooldown_seconds: float,
	jitter_seconds: float,
) -> bytes:
	xml_payload, _, _ = fetch_bytes(
		url=url,
		timeout_seconds=timeout_seconds,
		max_attempts=max_attempts,
		base_cooldown_seconds=base_cooldown_seconds,
		jitter_seconds=jitter_seconds,
		accept_header="application/xml,text/xml;q=0.9,*/*;q=0.8",
	)
	return xml_payload


def parse_sitemap_index(xml_payload: bytes) -> list[SitemapFile]:
	root = ET.fromstring(xml_payload)
	items: list[SitemapFile] = []
	for node in root:
		if xml_local_name(node.tag) != "sitemap":
			continue
		loc = None
		lastmod = None
		for child in node:
			name = xml_local_name(child.tag)
			text = (child.text or "").strip()
			if name == "loc":
				loc = text
			elif name == "lastmod":
				lastmod = text or None
		if loc:
			items.append(SitemapFile(loc=loc, lastmod=lastmod))
	return items


def parse_sitemap_urlset(xml_payload: bytes) -> list[SitemapArticle]:
	root = ET.fromstring(xml_payload)
	items: list[SitemapArticle] = []
	for node in root:
		if xml_local_name(node.tag) != "url":
			continue

		loc = None
		lastmod = None
		image_loc = None
		for child in node:
			name = xml_local_name(child.tag)
			if name == "loc":
				loc = (child.text or "").strip() or None
			elif name == "lastmod":
				lastmod = (child.text or "").strip() or None
			elif name == "image":
				for image_child in child:
					if xml_local_name(image_child.tag) == "loc":
						image_loc = (image_child.text or "").strip() or None

		if loc:
			items.append(SitemapArticle(loc=loc, lastmod=lastmod, image_loc=image_loc))
	return items


def parse_root_tag(xml_payload: bytes) -> str:
	root = ET.fromstring(xml_payload)
	return xml_local_name(root.tag)


def discover_month_index_urls(sitemap_root: str, target_date: date) -> list[str]:
	y = target_date.year
	m = f"{target_date.month:02d}"
	root = sitemap_root.rstrip("/")
	return [
		f"{root}/sitemap.xml",
		f"{root}/index.xml",
		f"{root}/{y}/{m}/index.xml",
		f"{root}/{y}/{m}/sitemap.xml",
	]


def is_target_day_sitemap(url: str, target_date: date) -> bool:
	marker = f"/{target_date.year}/{target_date.month:02d}/{target_date.day:02d}_"
	return marker in url


SITEMAP_LOC_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})_(\d+)\.xml$")


def sitemap_sort_key(sitemap: SitemapFile) -> tuple[datetime, int]:
	if sitemap.lastmod:
		try:
			if "T" in sitemap.lastmod:
				return datetime.fromisoformat(sitemap.lastmod.replace("Z", "+00:00")), 0
			return datetime.fromisoformat(sitemap.lastmod + "T00:00:00+00:00"), 0
		except Exception:
			pass

	match = SITEMAP_LOC_RE.search(sitemap.loc)
	if match:
		year, month, day, seq = match.groups()
		return (
			datetime(int(year), int(month), int(day), tzinfo=timezone.utc),
			int(seq),
		)

	return datetime.fromtimestamp(0, tz=timezone.utc), 0


def ensure_tracking_tables(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS g1_sitemaps (
			sitemap_url TEXT PRIMARY KEY,
			sitemap_lastmod TEXT,
			target_date DATE,
			discovered_at TIMESTAMPTZ NOT NULL,
			processed_at TIMESTAMPTZ NOT NULL,
			urls_in_sitemap INTEGER NOT NULL DEFAULT 0,
			extracted_ok INTEGER NOT NULL DEFAULT 0,
			extracted_failed INTEGER NOT NULL DEFAULT 0
		)
		"""
	)
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS g1_articles (
			url TEXT PRIMARY KEY,
			sitemap_url TEXT REFERENCES g1_sitemaps(sitemap_url) ON DELETE SET NULL,
			sitemap_lastmod TEXT,
			sitemap_article_lastmod TEXT,
			sitemap_image_url TEXT,
			first_seen_at TIMESTAMPTZ NOT NULL,
			last_seen_at TIMESTAMPTZ NOT NULL,
			fetch_status TEXT,
			fetch_error TEXT,
			fetch_attempts INTEGER NOT NULL DEFAULT 0,
			http_status INTEGER,
			fetched_at TIMESTAMPTZ,
			final_url TEXT,
			extraction_status TEXT,
			extraction_error TEXT,
			extracted_at TIMESTAMPTZ,
			title TEXT,
			author TEXT,
			hostname TEXT,
			sitename TEXT,
			date_published TEXT,
			language TEXT,
			excerpt TEXT,
			categories TEXT[],
			tags TEXT[],
			text_content TEXT,
			raw_sitemap JSONB,
			raw_metadata JSONB
		)
		"""
	)
	conn.execute(
		"""
		CREATE INDEX IF NOT EXISTS idx_g1_articles_last_seen
		ON g1_articles(last_seen_at DESC)
		"""
	)
	conn.execute(
		"""
		CREATE INDEX IF NOT EXISTS idx_g1_articles_fetch_status
		ON g1_articles(fetch_status)
		"""
	)
	conn.commit()


def get_processed_sitemaps(conn) -> set[str]:
	rows = conn.execute("SELECT sitemap_url FROM g1_sitemaps").fetchall()
	return {row[0] for row in rows}


def mark_sitemap_processed(
	conn,
	sitemap_url: str,
	sitemap_lastmod: str | None,
	target_date: date,
	urls_in_sitemap: int,
	extracted_ok: int,
	extracted_failed: int,
) -> None:
	conn.execute(
		"""
		INSERT INTO g1_sitemaps (
			sitemap_url,
			sitemap_lastmod,
			target_date,
			discovered_at,
			processed_at,
			urls_in_sitemap,
			extracted_ok,
			extracted_failed
		)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
		ON CONFLICT (sitemap_url)
		DO UPDATE SET
			sitemap_lastmod = EXCLUDED.sitemap_lastmod,
			target_date = EXCLUDED.target_date,
			discovered_at = EXCLUDED.discovered_at,
			processed_at = EXCLUDED.processed_at,
			urls_in_sitemap = EXCLUDED.urls_in_sitemap,
			extracted_ok = EXCLUDED.extracted_ok,
			extracted_failed = EXCLUDED.extracted_failed
		""",
		(
			sitemap_url,
			sitemap_lastmod,
			target_date.isoformat(),
			utc_now_iso(),
			utc_now_iso(),
			urls_in_sitemap,
			extracted_ok,
			extracted_failed,
		),
	)
	conn.commit()


def upsert_sitemap_discovered(conn, sitemap: SitemapFile, target_date: date) -> None:
	conn.execute(
		"""
		INSERT INTO g1_sitemaps (
			sitemap_url,
			sitemap_lastmod,
			target_date,
			discovered_at,
			processed_at,
			urls_in_sitemap,
			extracted_ok,
			extracted_failed
		)
		VALUES (%s, %s, %s, %s, %s, 0, 0, 0)
		ON CONFLICT (sitemap_url)
		DO UPDATE SET
			sitemap_lastmod = EXCLUDED.sitemap_lastmod,
			target_date = EXCLUDED.target_date,
			discovered_at = EXCLUDED.discovered_at
		""",
		(
			sitemap.loc,
			sitemap.lastmod,
			target_date.isoformat(),
			utc_now_iso(),
			utc_now_iso(),
		),
	)


def upsert_article_seed(conn, sitemap: SitemapFile, article: SitemapArticle, now_iso: str) -> None:
	raw_sitemap = {
		"sitemap_url": sitemap.loc,
		"sitemap_lastmod": sitemap.lastmod,
		"article_lastmod": article.lastmod,
		"image_loc": article.image_loc,
	}
	with conn.cursor() as cur:
		cur.execute(
			"""
			INSERT INTO g1_articles (
				url,
				sitemap_url,
				sitemap_lastmod,
				sitemap_article_lastmod,
				sitemap_image_url,
				first_seen_at,
				last_seen_at,
				raw_sitemap
			)
			VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
			ON CONFLICT (url)
			DO UPDATE SET
				sitemap_url = EXCLUDED.sitemap_url,
				sitemap_lastmod = EXCLUDED.sitemap_lastmod,
				sitemap_article_lastmod = EXCLUDED.sitemap_article_lastmod,
				sitemap_image_url = EXCLUDED.sitemap_image_url,
				last_seen_at = EXCLUDED.last_seen_at,
				raw_sitemap = EXCLUDED.raw_sitemap
			""",
			(
				article.loc,
				sitemap.loc,
				sitemap.lastmod,
				article.lastmod,
				article.image_loc,
				now_iso,
				now_iso,
				json.dumps(raw_sitemap, ensure_ascii=False),
			),
		)


def get_successfully_extracted_urls(conn, urls: list[str]) -> set[str]:
	if not urls:
		return set()
	with conn.cursor() as cur:
		cur.execute(
			"""
			SELECT url
			FROM g1_articles
			WHERE url = ANY(%s)
			  AND extraction_status = 'ok'
			  AND text_content IS NOT NULL
			  AND text_content <> ''
			""",
			(urls,),
		)
		return {row[0] for row in cur.fetchall()}


def normalize_trafilatura_metadata(metadata: object, final_url: str) -> dict:
	def make_json_safe(value: object):
		if value is None or isinstance(value, (str, int, float, bool)):
			return value
		if isinstance(value, datetime):
			return value.isoformat()
		if isinstance(value, date):
			return value.isoformat()
		if isinstance(value, dict):
			return {str(k): make_json_safe(v) for k, v in value.items()}
		if isinstance(value, (list, tuple, set)):
			return [make_json_safe(v) for v in value]
		return str(value)

	if isinstance(metadata, dict):
		meta = dict(metadata)
	elif hasattr(metadata, "as_dict"):
		meta = metadata.as_dict() or {}
	else:
		meta = {}

	if not isinstance(meta, dict):
		meta = {}

	meta.setdefault("url", final_url)
	return make_json_safe(meta)


def extract_article_metadata(html_text: str, final_url: str) -> tuple[str, dict, str | None]:
	try:
		metadata = trafilatura.bare_extraction(
			html_text,
			url=final_url,
			with_metadata=True,
			favor_precision=True,
		)
		meta = normalize_trafilatura_metadata(metadata, final_url)
		text_content = (meta.get("text") or "").strip()
		if not text_content:
			json_payload = trafilatura.extract(
				html_text,
				url=final_url,
				output_format="json",
				with_metadata=True,
				favor_precision=True,
			)
			if json_payload:
				parsed = json.loads(json_payload)
				if isinstance(parsed, dict):
					for k, v in parsed.items():
						meta.setdefault(k, v)
					text_content = (meta.get("text") or "").strip()

		if not text_content:
			return "no_content", meta, "article text not found"
		return "ok", meta, None
	except Exception as exc:
		return "extract_failed", {}, str(exc)


def to_text_array(value: object) -> list[str] | None:
	if value is None:
		return None
	if isinstance(value, list):
		items = [str(v).strip() for v in value if str(v).strip()]
		return items or None
	if isinstance(value, str):
		parts = [part.strip() for part in value.split(",") if part.strip()]
		return parts or None
	return None


def update_article_fetch_error(
	conn,
	url: str,
	status: str,
	error_message: str,
	http_status: int | None,
	final_url: str | None,
) -> None:
	conn.execute(
		"""
		UPDATE g1_articles
		SET fetch_status = %s,
			fetch_error = %s,
			fetch_attempts = COALESCE(fetch_attempts, 0) + 1,
			http_status = %s,
			fetched_at = %s,
			final_url = COALESCE(%s, final_url)
		WHERE url = %s
		""",
		(status, error_message, http_status, utc_now_iso(), final_url, url),
	)


def update_article_extraction(
	conn,
	url: str,
	http_status: int,
	final_url: str,
	extraction_status: str,
	extraction_error: str | None,
	meta: dict,
) -> None:
	conn.execute(
		"""
		UPDATE g1_articles
		SET fetch_status = %s,
			fetch_error = NULL,
			fetch_attempts = COALESCE(fetch_attempts, 0) + 1,
			http_status = %s,
			fetched_at = %s,
			final_url = %s,
			extraction_status = %s,
			extraction_error = %s,
			extracted_at = %s,
			title = %s,
			author = %s,
			hostname = %s,
			sitename = %s,
			date_published = %s,
			language = %s,
			excerpt = %s,
			categories = %s,
			tags = %s,
			text_content = %s,
			raw_metadata = %s::jsonb
		WHERE url = %s
		""",
		(
			"ok",
			http_status,
			utc_now_iso(),
			final_url,
			extraction_status,
			extraction_error,
			utc_now_iso(),
			(meta.get("title") or None),
			(meta.get("author") or None),
			(meta.get("hostname") or get_domain(final_url) or None),
			(meta.get("sitename") or None),
			(meta.get("date") or meta.get("published") or None),
			(meta.get("language") or None),
			(meta.get("description") or meta.get("excerpt") or None),
			to_text_array(meta.get("categories")),
			to_text_array(meta.get("tags")),
			(meta.get("text") or None),
			json.dumps(meta, ensure_ascii=False),
			url,
		),
	)


def fetch_and_extract_article(
	conn,
	article_url: str,
	timeout_seconds: int,
	max_attempts: int,
	base_cooldown_seconds: float,
	jitter_seconds: float,
) -> str:
	try:
		html_bytes, final_url, status = fetch_bytes(
			url=article_url,
			timeout_seconds=timeout_seconds,
			max_attempts=max_attempts,
			base_cooldown_seconds=base_cooldown_seconds,
			jitter_seconds=jitter_seconds,
			accept_header="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
		)
		content = html_bytes.decode("utf-8", errors="replace")
		extraction_status, meta, extraction_error = extract_article_metadata(content, final_url)
		update_article_extraction(
			conn=conn,
			url=article_url,
			http_status=status,
			final_url=final_url,
			extraction_status=extraction_status,
			extraction_error=extraction_error,
			meta=meta,
		)
		return extraction_status
	except urllib.error.HTTPError as exc:
		status = "forbidden" if exc.code == 403 else "not_found" if exc.code == 404 else f"http_{exc.code}"
		update_article_fetch_error(
			conn,
			url=article_url,
			status=status,
			error_message=f"HTTP {exc.code}",
			http_status=exc.code,
			final_url=None,
		)
		return status
	except Exception as exc:
		update_article_fetch_error(
			conn,
			url=article_url,
			status="download_failed",
			error_message=str(exc),
			http_status=None,
			final_url=None,
		)
		return "download_failed"


def resolve_sitemap_files(
	index_url: str | None,
	sitemap_root: str,
	target_date: date,
	timeout_seconds: int,
	max_attempts: int,
	base_cooldown_seconds: float,
	jitter_seconds: float,
) -> list[SitemapFile]:
	# Path entrypoint: root sitemap index -> sitemap files -> article URLs.
	if index_url:
		xml_payload = fetch_xml(
			index_url,
			timeout_seconds=timeout_seconds,
			max_attempts=max_attempts,
			base_cooldown_seconds=base_cooldown_seconds,
			jitter_seconds=jitter_seconds,
		)
		root_tag = parse_root_tag(xml_payload)
		if root_tag == "urlset":
			return [SitemapFile(loc=index_url, lastmod=None)]
		return parse_sitemap_index(xml_payload)

	# Prefer the canonical G1 root index first.
	canonical_index = f"{sitemap_root.rstrip('/')}/sitemap.xml"
	try:
		xml_payload = fetch_xml(
			canonical_index,
			timeout_seconds=timeout_seconds,
			max_attempts=max_attempts,
			base_cooldown_seconds=base_cooldown_seconds,
			jitter_seconds=jitter_seconds,
		)
		root_tag = parse_root_tag(xml_payload)
		if root_tag == "sitemapindex":
			return parse_sitemap_index(xml_payload)
		if root_tag == "urlset":
			return [SitemapFile(loc=canonical_index, lastmod=None)]
	except Exception as exc:
		logging.info("Canonical index failed: %s (%s)", canonical_index, exc)

	for candidate in discover_month_index_urls(sitemap_root, target_date):
		if candidate == canonical_index:
			continue
		try:
			xml_payload = fetch_xml(
				candidate,
				timeout_seconds=timeout_seconds,
				max_attempts=max_attempts,
				base_cooldown_seconds=base_cooldown_seconds,
				jitter_seconds=jitter_seconds,
			)
			root_tag = parse_root_tag(xml_payload)
			if root_tag == "sitemapindex":
				return parse_sitemap_index(xml_payload)
			if root_tag == "urlset":
				return [SitemapFile(loc=candidate, lastmod=None)]
		except Exception as exc:
			logging.info("Index discovery candidate failed: %s (%s)", candidate, exc)
			continue

	raise RuntimeError(
		"Could not discover a valid sitemap index automatically. Pass --index-url explicitly."
	)


def run(
	db_dsn: str,
	target_date: date,
	index_url: str | None,
	sitemap_root: str,
	max_sitemaps: int | None,
	max_articles_per_sitemap: int | None,
	timeout_seconds: int,
	max_attempts: int,
	sitemap_base_cooldown_seconds: float,
	sitemap_jitter_seconds: float,
	article_base_cooldown_seconds: float,
	article_jitter_seconds: float,
	dry_run: bool,
	reprocess: bool,
	backward_from: date | None = None,
) -> None:
	with psycopg.connect(db_dsn) as conn:
		ensure_tracking_tables(conn)

		sitemap_files = resolve_sitemap_files(
			index_url=index_url,
			sitemap_root=sitemap_root,
			target_date=target_date,
			timeout_seconds=timeout_seconds,
			max_attempts=max_attempts,
			base_cooldown_seconds=sitemap_base_cooldown_seconds,
			jitter_seconds=sitemap_jitter_seconds,
		)

		daily_sitemaps = list(sitemap_files)
		daily_sitemaps.sort(key=sitemap_sort_key, reverse=True)

		# If backward_from is provided, filter sitemaps to only include those on or before that date.
		if backward_from is not None:
			cutoff_datetime = datetime(
				backward_from.year,
				backward_from.month,
				backward_from.day,
				tzinfo=timezone.utc,
			)
			daily_sitemaps = [s for s in daily_sitemaps if sitemap_sort_key(s)[0] <= cutoff_datetime]
			logging.info("Backward mode: filtering sitemaps to date <= %s", backward_from.isoformat())

		if max_sitemaps and max_sitemaps > 0:
			daily_sitemaps = daily_sitemaps[:max_sitemaps]

		if not daily_sitemaps:
			logging.info("No sitemap files found.")
			return

		logging.info("Found %d sitemap files (processing newest first).", len(daily_sitemaps))

		total_urls_seen = 0
		total_ok = 0
		total_failed = 0

		for i, sitemap in enumerate(daily_sitemaps, start=1):
			xml_payload = fetch_xml(
				sitemap.loc,
				timeout_seconds=timeout_seconds,
				max_attempts=max_attempts,
				base_cooldown_seconds=sitemap_base_cooldown_seconds,
				jitter_seconds=sitemap_jitter_seconds,
			)
			articles = parse_sitemap_urlset(xml_payload)

			if not dry_run:
				upsert_sitemap_discovered(conn, sitemap, target_date)

			now_iso = utc_now_iso()
			for article in articles:
				if not dry_run:
					upsert_article_seed(conn, sitemap, article, now_iso)

			pending_articles = articles
			if not dry_run and not reprocess:
				success_urls = get_successfully_extracted_urls(conn, [a.loc for a in articles])
				pending_articles = [a for a in articles if a.loc not in success_urls]

			if max_articles_per_sitemap and max_articles_per_sitemap > 0:
				pending_articles = pending_articles[:max_articles_per_sitemap]

			total_urls_seen += len(articles)
			sitemap_ok = 0
			sitemap_failed = 0

			if not pending_articles:
				logging.info(
					"[%d/%d] sitemap=%s fully scraped already (urls=%d)",
					i,
					len(daily_sitemaps),
					sitemap.loc,
					len(articles),
				)
				if not dry_run:
					mark_sitemap_processed(
						conn=conn,
						sitemap_url=sitemap.loc,
						sitemap_lastmod=sitemap.lastmod,
						target_date=target_date,
						urls_in_sitemap=len(articles),
						extracted_ok=len(articles),
						extracted_failed=0,
					)
				randomized_sleep(sitemap_base_cooldown_seconds, sitemap_jitter_seconds)
				continue

			for article_idx, article in enumerate(pending_articles, start=1):
				if dry_run:
					logging.info(
						"[%d/%d][%d/%d] dry-run url=%s",
						i,
						len(daily_sitemaps),
						article_idx,
						len(pending_articles),
						article.loc,
					)
					continue

				result = fetch_and_extract_article(
					conn=conn,
					article_url=article.loc,
					timeout_seconds=timeout_seconds,
					max_attempts=max_attempts,
					base_cooldown_seconds=article_base_cooldown_seconds,
					jitter_seconds=article_jitter_seconds,
				)
				conn.commit()

				if result == "ok":
					sitemap_ok += 1
					total_ok += 1
				else:
					sitemap_failed += 1
					total_failed += 1

				logging.info(
					"[%d/%d][%d/%d] status=%s url=%s",
					i,
					len(daily_sitemaps),
					article_idx,
					len(pending_articles),
					result,
					article.loc,
				)

				randomized_sleep(article_base_cooldown_seconds, article_jitter_seconds)

			if not dry_run:
				mark_sitemap_processed(
					conn=conn,
					sitemap_url=sitemap.loc,
					sitemap_lastmod=sitemap.lastmod,
					target_date=target_date,
					urls_in_sitemap=len(articles),
					extracted_ok=sitemap_ok,
					extracted_failed=sitemap_failed,
				)

			logging.info(
				"[%d/%d] sitemap=%s | total_urls=%d | pending=%d | ok=%d | failed=%d | dry_run=%s",
				i,
				len(daily_sitemaps),
				sitemap.loc,
				len(articles),
				len(pending_articles),
				sitemap_ok,
				sitemap_failed,
				dry_run,
			)

			randomized_sleep(sitemap_base_cooldown_seconds, sitemap_jitter_seconds)

		logging.info(
			"Done. sitemaps=%d urls_seen=%d ok=%d failed=%d dry_run=%s",
			len(daily_sitemaps),
			total_urls_seen,
			total_ok,
			total_failed,
			dry_run,
		)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Traverse G1 sitemap index pages, process all discovered sitemap files (newest first), "
			"extract content and metadata with trafilatura, and persist everything in dedicated G1 tables."
		)
	)
	parser.add_argument(
		"--db-dsn",
		default=DEFAULT_DB_DSN,
		help="PostgreSQL DSN (or set PG_DSN env var).",
	)
	parser.add_argument(
		"--date",
		default=date.today().isoformat(),
		help="Reference date in YYYY-MM-DD for automatic index discovery fallback (default: today).",
	)
	parser.add_argument(
		"--index-url",
		default=DEFAULT_G1_INDEX_URL,
		help="Sitemap index URL entrypoint (default: g1 root sitemap index).",
	)
	parser.add_argument(
		"--sitemap-root",
		default=DEFAULT_G1_SITEMAP_ROOT,
		help="Sitemap root used for automatic index discovery.",
	)
	parser.add_argument(
		"--max-sitemaps",
		type=int,
		default=None,
		help="Optional cap of daily sitemap files to process.",
	)
	parser.add_argument(
		"--max-articles-per-sitemap",
		type=int,
		default=None,
		help="Optional cap of article URLs processed per sitemap file.",
	)
	parser.add_argument(
		"--timeout-seconds",
		type=int,
		default=20,
		help="HTTP timeout per request.",
	)
	parser.add_argument(
		"--max-attempts",
		type=int,
		default=4,
		help="Max retries per sitemap request.",
	)
	parser.add_argument(
		"--sitemap-base-cooldown-seconds",
		type=float,
		default=1.2,
		help="Base cooldown after each sitemap request.",
	)
	parser.add_argument(
		"--sitemap-jitter-seconds",
		type=float,
		default=2.8,
		help="Random jitter added to sitemap cooldown.",
	)
	parser.add_argument(
		"--article-base-cooldown-seconds",
		type=float,
		default=2.0,
		help="Base cooldown after each article request.",
	)
	parser.add_argument(
		"--article-jitter-seconds",
		type=float,
		default=1.0,
		help="Random jitter added to article cooldown.",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Parse and count URLs without inserting rows.",
	)
	parser.add_argument(
		"--reprocess",
		action="store_true",
		help="Reprocess sitemap files even if already tracked as processed.",
	)
	parser.add_argument(
		"--backward-from",
		type=parse_iso_date,
		default=None,
		help="Only process sitemaps from this date backwards (YYYY-MM-DD). Never forwards.",
	)
	return parser.parse_args()


def main() -> None:
	configure_logging()
	args = parse_args()

	if not args.db_dsn:
		raise SystemExit("Missing PostgreSQL DSN. Pass --db-dsn or set PG_DSN.")

	try:
		target_date = date.fromisoformat(args.date)
	except ValueError as exc:
		raise SystemExit(f"Invalid --date value: {args.date}") from exc

	run(
		db_dsn=args.db_dsn,
		target_date=target_date,
		index_url=args.index_url,
		sitemap_root=args.sitemap_root,
		max_sitemaps=args.max_sitemaps,
		max_articles_per_sitemap=args.max_articles_per_sitemap,
		timeout_seconds=max(5, args.timeout_seconds),
		max_attempts=max(1, args.max_attempts),
		sitemap_base_cooldown_seconds=max(0.0, args.sitemap_base_cooldown_seconds),
		sitemap_jitter_seconds=max(0.0, args.sitemap_jitter_seconds),
		article_base_cooldown_seconds=max(0.0, args.article_base_cooldown_seconds),
		article_jitter_seconds=max(0.0, args.article_jitter_seconds),
		dry_run=args.dry_run,
		reprocess=args.reprocess,
		backward_from=args.backward_from,
	)


if __name__ == "__main__":
	main()
