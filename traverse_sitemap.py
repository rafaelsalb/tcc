from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import http.client
import threading
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
from datetime import date, datetime, timedelta, timezone

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


def sleep_with_jitter(base_seconds: float, jitter_sigma: float) -> None:
	"""Fixed backoff base with gaussian jitter. (Replaces randomized_sleep,
	which ignored its jitter argument entirely and always used sigma=1.)"""
	time.sleep(max(0.1, base_seconds + np.random.normal(0.0, jitter_sigma)))


class RateGovernor:
	"""Token-bucket pacing with adaptive (AIMD) probing toward g1.globo.com's
	unknown rate ceiling.

	Every request is admitted at `rps` tokens/second via acquire(). While a
	run is clean, the rate rises by `ramp_factor` after each `ramp_requests`
	successes. Throttling signals — HTTP 429/403/503 are hard; timeouts,
	resets and IncompleteRead are soft — cut the rate, and hard signals also
	pause all admissions for a penalty window and permanently ratchet
	`safe_ceiling` below the rate that produced them, so the band that got
	flagged is never re-entered during this session. The final state() is the
	measured comfort ceiling; production backlog runs should sit ~25% under
	it (the rate the edge tolerates varies by IP, time of day and load).
	"""

	HARD_SIGNALS = {429, 403, 503}

	def __init__(
		self,
		start_rps: float,
		min_rps: float,
		max_rps: float,
		*,
		fixed: bool = False,
		ramp_requests: int = 120,
		ramp_factor: float = 1.12,
		cut_factor: float = 0.5,
		ceiling_cut: float = 0.8,
		hard_penalty_seconds: float = 90.0,
	) -> None:
		self.rps = min(max(float(start_rps), float(min_rps)), float(max_rps))
		self.min_rps = float(min_rps)
		self.safe_ceiling = float(max_rps)
		self.fixed = fixed
		self.ramp_requests = int(ramp_requests)
		self.ramp_factor = float(ramp_factor)
		self.cut_factor = float(cut_factor)
		self.ceiling_cut = float(ceiling_cut)
		self.hard_penalty_seconds = float(hard_penalty_seconds)
		self.consecutive_hard = 0
		self._lock = threading.Lock()
		self._condition = threading.Condition(self._lock)
		self._next_slot = time.monotonic()
		self.oks = 0
		self.signals = 0

	def acquire(self) -> None:
		"""Block until it is this caller's turn to start a request."""
		with self._condition:
			while True:
				now = time.monotonic()
				if now >= self._next_slot:
					self._next_slot += 1.0 / self.rps
					return
				self._condition.wait(timeout=max(0.02, self._next_slot - now))

	def on_success(self) -> None:
		with self._lock:
			self.oks += 1
			if self.oks < self.ramp_requests:
				return
			# a sustained clean window resets the ramp cycle and forgives any
			# escalation built up while brushing the ceiling
			self.oks = 0
			self.consecutive_hard = 0
			if self.fixed or self.rps >= self.safe_ceiling:
				return
			self.rps = min(self.safe_ceiling, self.rps * self.ramp_factor)
			logging.info(
				"Clean window — rate raised to %.2f req/s (ceiling %.2f)", self.rps, self.safe_ceiling
			)

	def on_signal(self, status: int | None = None, detail: str = "") -> float:
		"""Report a throttling signal. Returns the penalty pause in seconds
		the *signalling* request already accounted for; future admissions
		wait it out inside acquire()."""
		with self._condition:
			hard = status in self.HARD_SIGNALS
			previous = self.rps
			self.signals += 1
			self.oks = 0
			self.rps = max(self.min_rps, min(previous * self.cut_factor, self.safe_ceiling))
			if hard:
				# Escalating restraint: each consecutive hard signal doubles the
				# pause (90s -> 3min -> 6min ... capped at 30min), so a run that
				# keeps brushing the ceiling leans further back instead of
				# pinning against it. A clean ramp cycle resets the escalation.
				self.consecutive_hard += 1
				penalty = min(
					1800.0,
					self.hard_penalty_seconds * (2.0 ** (self.consecutive_hard - 1)),
				)
				self.safe_ceiling = max(self.min_rps, previous * self.ceiling_cut)
				self.rps = max(self.min_rps, min(self.rps, self.safe_ceiling))
				logging.warning(
					"Throttled (HTTP %s; %s) — rate cut to %.2f req/s, ceiling ratcheted to %.2f, admissions paused %.0fs (escalation %d)",
					status,
					detail or "unspecified",
					self.rps,
					self.safe_ceiling,
					penalty,
					self.consecutive_hard,
				)
				self._next_slot = max(self._next_slot, time.monotonic() + penalty)
				self._condition.notify_all()
				return penalty
			logging.warning(
				"Soft trouble (%s) — rate cut to %.2f req/s", detail or "unspecified", self.rps
			)
			self._condition.notify_all()
			return 0.0

	def state(self) -> str:
		with self._lock:
			return (
				f"rps={self.rps:.2f} safe_ceiling={self.safe_ceiling:.2f} "
				f"clean={self.oks}/{self.ramp_requests} signals={self.signals}"
			)


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
			sleep_with_jitter(backoff, jitter_seconds)
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
			sleep_with_jitter(backoff, jitter_seconds)
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
			sleep_with_jitter(backoff, jitter_seconds)

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


def extract_article_from_network(
	article_url: str,
	timeout_seconds: int,
	max_attempts: int,
	base_cooldown_seconds: float,
	jitter_seconds: float,
	governor: RateGovernor,
) -> dict:
	"""Fetch and extract one article WITHOUT touching the database — network
	work dispatches to worker threads and the (not thread-safe) psycopg
	connection is used only by the main thread afterwards."""
	try:
		governor.acquire()
		html_bytes, final_url, status = fetch_bytes(
			url=article_url,
			timeout_seconds=timeout_seconds,
			max_attempts=max_attempts,
			base_cooldown_seconds=base_cooldown_seconds,
			jitter_seconds=jitter_seconds,
			accept_header="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
		)
	except urllib.error.HTTPError as exc:
		code = exc.code
		if code in governor.HARD_SIGNALS or code >= 500:
			governor.on_signal(code, detail="article fetch")
		else:
			# URL-specific outcomes (404, other 4xx) say nothing about pacing
			governor.on_success()
		return {
			"status": "forbidden" if code == 403 else "not_found" if code == 404 else f"http_{code}",
			"http_status": code,
			"final_url": None,
			"meta": None,
			"error": f"HTTP {code}",
		}
	except Exception as exc:
		governor.on_signal(None, detail=f"article transport ({type(exc).__name__})")
		return {
			"status": "download_failed",
			"http_status": None,
			"final_url": None,
			"meta": None,
			"error": str(exc),
		}

	governor.on_success()
	content = html_bytes.decode("utf-8", errors="replace")
	extraction_status, meta, extraction_error = extract_article_metadata(content, final_url)
	return {
		"status": extraction_status,
		"http_status": status,
		"final_url": final_url,
		"meta": meta,
		"error": extraction_error,
	}


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


def process_sitemap_file(
	conn,
	sitemap: SitemapFile,
	xml_payload: bytes,
	target_date: date,
	reprocess: bool,
	max_articles_per_sitemap: int | None,
	dry_run: bool,
	concurrency: int,
	governor: "RateGovernor",
	category: str,
	timeout_seconds: int,
	max_attempts: int,
	article_base_cooldown_seconds: float,
	article_jitter_seconds: float,
) -> dict:
	"""Parse one fetched daily-sitemap file, persist its seeds and article
	rows, and mark it processed. Returns counts {'urls', 'ok', 'failed'}; the
	pending-articles pool hides network latency while the governor keeps the
	aggregate pace."""
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

	sitemap_ok = 0
	sitemap_failed = 0

	if not pending_articles:
		logging.info(
			"%s sitemap=%s fully scraped already (urls=%d)",
			category, sitemap.loc, len(articles),
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
		return {"urls": len(articles), "ok": 0, "failed": 0}

	if dry_run:
		for article_idx, article in enumerate(pending_articles, start=1):
			logging.info(
				"%s[%d/%d] dry-run url=%s",
				category,
				article_idx,
				len(pending_articles),
				article.loc,
			)
	else:
		with concurrent.futures.ThreadPoolExecutor(
			max_workers=concurrency, thread_name_prefix="g1-fetch"
		) as pool:
			futures_map = {
				pool.submit(
					extract_article_from_network,
					article.loc,
					timeout_seconds,
					max_attempts,
					article_base_cooldown_seconds,
					article_jitter_seconds,
					governor,
				): article.loc
				for article in pending_articles
			}
			for article_idx, future in enumerate(
				concurrent.futures.as_completed(futures_map), start=1
			):
				url = futures_map[future]
				try:
					outcome = future.result()
				except Exception as exc:  # defensive; the worker returns dicts itself
					outcome = {
						"status": "download_failed",
						"http_status": None,
						"final_url": None,
						"meta": None,
						"error": str(exc),
					}

				if outcome["status"] == "ok":
					update_article_extraction(
						conn=conn,
						url=url,
						http_status=outcome["http_status"],
						final_url=outcome["final_url"],
						extraction_status="ok",
						extraction_error=None,
						meta=outcome["meta"],
					)
					sitemap_ok += 1
				else:
					update_article_fetch_error(
						conn=conn,
						url=url,
						status=outcome["status"],
						error_message=outcome["error"] or outcome["status"],
						http_status=outcome["http_status"],
						final_url=outcome["final_url"],
					)
					sitemap_failed += 1
				conn.commit()

				logging.info(
					"%s[%d/%d] status=%s url=%s",
					category,
					article_idx,
					len(pending_articles),
					outcome["status"],
					url,
				)

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
		"%s sitemap=%s | total_urls=%d | pending=%d | ok=%d | failed=%d | dry_run=%s",
		category,
		sitemap.loc,
		len(articles),
		len(pending_articles),
		sitemap_ok,
		sitemap_failed,
		dry_run,
	)
	return {"urls": len(articles), "ok": sitemap_ok, "failed": sitemap_failed}


@dataclass(frozen=True)
class CrawlLane:
	"""One lane of the multi-directional date sweep: a start date and the
	direction it starts walking ((-1 = backward into the past, +1 = toward
	today)). CLI --lanes items: 'YYYY-MM-DD' (forward) or 'YYYY-MM-DD:backward'."""

	name: str
	start: date
	direction: int


def parse_lane_spec(spec: str) -> list[CrawlLane]:
	"""Parse --lanes value into lanes, validating dates and directions."""
	lanes: list[CrawlLane] = []
	for index, item in enumerate((part.strip() for part in spec.split(",")), start=1):
		if not item:
			continue
		try:
			date_text, _, direction_text = item.partition(":")
			start = date.fromisoformat(date_text.strip())
		except ValueError as exc:
			raise ValueError(
				f"Invalid --lanes item {index} ('{item}'); expected 'YYYY-MM-DD[:forward|backward]'."
			) from exc
		direction_text = (direction_text or "forward").strip().lower()
		if direction_text not in ("forward", "backward"):
			raise ValueError(
				f"Invalid direction '{direction_text}' in --lanes item {index} ('{item}'); "
				"use 'forward' or 'backward'."
			)
		lanes.append(
			CrawlLane(
				name=f"lane{index}",
				start=start,
				direction=1 if direction_text == "forward" else -1,
			)
		)
	if not lanes:
		raise ValueError("--lanes did not contain any lane items.")
	return lanes


class SitemapDiscovery:
	"""Root-index listing cache for the lane sweep. The canonical G1 root
	sitemap index lists every daily file across the whole archive (7k+ days
	back to 2003), so it is the single discovery source: no per-month indexes
	exist. The listing is refetched periodically so days published during a
	Long run appear at the head."""

	ROOT_REFRESH_SECONDS = 30 * 60.0
	UNAVAILABLE_RETRY_SLEEP_SECONDS = 30.0
	MAX_UNAVAILABLE_STREAK = 5
	# A lane in transit walks at most this many days toward the peer snapshot
	# before resuming normal stepping (guards against chasing a moving peer).
	MAX_TRANSIT_DAYS = 1500

	def __init__(
		self,
		sitemap_root: str,
		governor: "RateGovernor",
		timeout_seconds: int,
		max_attempts: int,
		sitemap_base_cooldown_seconds: float,
		sitemap_jitter_seconds: float,
	):
		self.sitemap_root = sitemap_root.rstrip("/")
		self.governor = governor
		self.timeout_seconds = timeout_seconds
		self.max_attempts = max_attempts
		self.base_cooldown = sitemap_base_cooldown_seconds
		self.jitter = sitemap_jitter_seconds
		self._lock = threading.Lock()
		self._root: dict | None = None

	def _fetch_root(self) -> dict:
		url = f"{self.sitemap_root}/sitemap.xml"
		self.governor.acquire()
		try:
			xml_payload = fetch_xml(
				url,
				timeout_seconds=self.timeout_seconds,
				max_attempts=self.max_attempts,
				base_cooldown_seconds=self.base_cooldown,
				jitter_seconds=self.jitter,
			)
		except urllib.error.HTTPError as exc:
			self.governor.on_signal(exc.code, detail="root index fetch")
			# failures are NOT cached: the next root_days() call refetches, so
			# the lanes' unavailable-retry streak waits out a real throttle
			return {"status": "unavailable", "days": {}, "fetched_at": time.monotonic()}
		except (urllib.error.URLError, TimeoutError, OSError) as exc:
			self.governor.on_signal(None, detail="root index fetch")
			return {"status": "unavailable", "days": {}, "fetched_at": time.monotonic()}
		self.governor.on_success()
		days: dict[date, list[SitemapFile]] = {}
		for sitemap_entry in parse_sitemap_index(xml_payload):
			match = SITEMAP_LOC_RE.search(sitemap_entry.loc)
			if not match:
				continue
			entry_day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
			days.setdefault(entry_day, []).append(sitemap_entry)
		entry = {"status": "ok", "days": days, "fetched_at": time.monotonic()}
		with self._lock:
			self._root = entry
		return entry

	def root_days(self) -> dict:
		with self._lock:
			entry = self._root
		if entry is not None and (time.monotonic() - entry["fetched_at"]) < self.ROOT_REFRESH_SECONDS:
			return entry
		return self._fetch_root()

	def files_for_day(self, day: date) -> list[SitemapFile] | None:
		"""Daily files for `day`; None when the listing is (still) unavailable —
		the caller retries; an empty list means the day has no sitemap (gap)."""
		root = self.root_days()
		if root["status"] != "ok":
			return None
		return root["days"].get(day, [])


def get_sitemap_completion_stats(conn, urls: list[str]) -> dict[str, tuple[int, int, int]]:
	"""Tracking-row counts for sitemap files; empty map for rows missing."""
	if not urls:
		return {}
	rows = conn.execute(
		"""
		SELECT sitemap_url, urls_in_sitemap, extracted_ok, extracted_failed
		FROM g1_sitemaps
		WHERE sitemap_url = ANY(%s)
		""",
		(urls,),
	).fetchall()
	return {row[0]: (row[1], row[2], row[3]) for row in rows}


def is_day_fully_processed(conn, files: list[SitemapFile]) -> bool:
	"""A day is done for sweep purposes when every listed daily file has a
	tracking row and all of its URLs reached a terminal fetch status."""
	if not files:
		return False
	stats = get_sitemap_completion_stats(conn, [f.loc for f in files])
	if len(stats) < len(files):
		return False
	return all(urls == ok + failed for urls, ok, failed in stats.values())


class LaneContext:
	"""Shared state for a --lanes run: mutable cursor/direction per lane, a
	claims map that keeps lanes from racing for the same day, and shared
	discovery caching. The peer handoff implements the 'boundary -> flip
	direction -> walk to the other worker's date' rule."""

	def __init__(self, lanes: list[CrawlLane]):
		self.runtimes: dict[str, dict] = {
			lane.name: {
				"lane": lane,
				"cursor": lane.start,
				"direction": lane.direction,
				"in_transit": False,
				"steps": 0,
			}
			for lane in lanes
		}
		self._lock = threading.Lock()
		self._claims: dict[date, str] = {}

	def cursor_of(self, lane_name: str) -> date:
		with self._lock:
			return self.runtimes[lane_name]["cursor"]

	def flip_target_for(self, lane_name: str) -> tuple[str, date] | None:
		"""The other lane whose current cursor the flipping lane walks to.
		Returns None for single-lane runs."""
		with self._lock:
			others = [
				(name, state["cursor"])
				for name, state in self.runtimes.items()
				if name != lane_name
			]
		return others[0] if others else None

	def claim(self, day: date, lane_name: str) -> bool:
		with self._lock:
			owner = self._claims.get(day)
		return owner is None or owner == lane_name

	def take_claim(self, day: date, lane_name: str) -> bool:
		with self._lock:
			owner = self._claims.get(day)
			if owner is not None and owner != lane_name:
				return False
			self._claims[day] = lane_name
			return True

	def release_claim(self, day: date, lane_name: str) -> None:
		with self._lock:
			if self._claims.get(day) == lane_name:
				self._claims.pop(day)


def run_lanes(
	db_dsn: str,
	lanes: list[CrawlLane],
	sitemap_root: str,
	governor: "RateGovernor",
	timeout_seconds: int,
	max_attempts: int,
	sitemap_base_cooldown_seconds: float,
	sitemap_jitter_seconds: float,
	article_base_cooldown_seconds: float,
	article_jitter_seconds: float,
	max_articles_per_sitemap: int | None,
	dry_run: bool,
	reprocess: bool,
	max_sitemaps: int | None,
	max_lane_steps: int,
	concurrency: int,
) -> None:
	"""Multi-lane date sweep. Each lane steps day by day in its direction over
	cached month listings; when a lane hits a boundary (candidate beyond
	today, or a month listing that is empty/unavailable) it flips direction
	and walks to the other lane's current date before continuing — refetching
	nothing that is already fully processed."""
	input_lanes = lanes
	context = LaneContext(input_lanes)
	discovery = SitemapDiscovery(
		sitemap_root=sitemap_root,
		governor=governor,
		timeout_seconds=timeout_seconds,
		max_attempts=max_attempts,
		sitemap_base_cooldown_seconds=sitemap_base_cooldown_seconds,
		sitemap_jitter_seconds=sitemap_jitter_seconds,
	)
	stop = threading.Event()
	done_files_lock = threading.Lock()
	done_files = [0]

	def processed_budget_reached() -> bool:
		if not max_sitemaps or max_sitemaps <= 0:
			return False
		with done_files_lock:
			return done_files[0] >= max_sitemaps

	def note_processed_file(count: int) -> None:
		if count <= 0:
			return
		with done_files_lock:
			done_files[0] += count
		if max_sitemaps and max_sitemaps > 0:
			with done_files_lock:
				if done_files[0] >= max_sitemaps:
					stop.set()

	def lane_loop(runtime: dict, lane_index: int) -> None:
		lane: CrawlLane = runtime["lane"]
		name = lane.name
		with psycopg.connect(db_dsn) as conn:
			ensure_tracking_tables(conn)
			while not stop.is_set() and runtime["steps"] < max_lane_steps:
				runtime["steps"] += 1
				today = date.today()
				direction: int = runtime["direction"]
				candidate = runtime["cursor"] + timedelta(days=direction)
				border_kind = None
				files: list[SitemapFile] | None = None
				if direction > 0 and candidate > today:
					border_kind = "upper boundary (beyond today)"
				else:
					root_status = discovery.root_days()["status"]
					if direction < 0 and root_status == "ok":
						floor_day = min(discovery.root_days()["days"])
						if candidate < floor_day:
							border_kind = f"lower boundary (archive floor at {floor_day.isoformat()})"
					if border_kind is None:
						files = discovery.files_for_day(candidate)
						if files is None:
							streak = runtime.get("unavailable_streak", 0) + 1
							runtime["unavailable_streak"] = streak
							if streak >= SitemapDiscovery.MAX_UNAVAILABLE_STREAK:
								border_kind = "lower boundary (root listing unavailable)"
							else:
								logging.info(
									"[%s] root listing unavailable — retrying in %.0fs (%d/%d)",
									name,
									SitemapDiscovery.UNAVAILABLE_RETRY_SLEEP_SECONDS,
									streak,
									SitemapDiscovery.MAX_UNAVAILABLE_STREAK,
								)
								time.sleep(SitemapDiscovery.UNAVAILABLE_RETRY_SLEEP_SECONDS)
								continue
						else:
							runtime["unavailable_streak"] = 0
							if not files:
								logging.info(
									"[%s] day %s: no sitemap listing in the index (gap day)",
									name,
									candidate.isoformat(),
								)
								runtime["cursor"] = candidate
								continue
				if border_kind is not None:
					# Boundary rule: flip direction and walk to the other
					# lane's current date (snapshot — the date at flip time;
					# the peer keeps moving and chasing it never terminates).
					# The damping sleep keeps a permanent boundary flip-flop
					# cheap (deep archive floor or fresh-nothing head).
					runtime["direction"] = -direction
					runtime["cursor"] = candidate
					runtime["in_transit"] = False
					peer = context.flip_target_for(name)
					time.sleep(60.0)
					if peer is None:
						logging.info(
							"[%s] hit %s — flipped direction to %s",
							name,
							border_kind,
							"forward" if runtime["direction"] > 0 else "backward",
						)
						continue
					peer_name, peer_cursor = peer
					runtime["in_transit"] = True
					runtime["transit_target"] = peer_cursor
					runtime["transit_days"] = 0
					logging.info(
						"[%s] hit %s — flipped to %s, transiting to %s (snapshot of %s at %s)",
						name,
						border_kind,
						"forward" if runtime["direction"] > 0 else "backward",
						peer_cursor.isoformat(),
						peer_name,
						runtime["cursor"].isoformat(),
					)
					continue

				if runtime["in_transit"]:
					target = runtime.get("transit_target")
					if target is None:
						runtime["in_transit"] = False
					else:
						runtime["transit_days"] = runtime.get("transit_days", 0) + 1
						behind_target = (
							direction > 0 and candidate < target
						) or (
							direction < 0 and candidate > target
						)
						if not behind_target or runtime["transit_days"] >= SitemapDiscovery.MAX_TRANSIT_DAYS:
							runtime["in_transit"] = False
							logging.info(
								"[%s] transit complete near %s (target %s, %d day(s)) — resuming %s",
								name,
								candidate.isoformat(),
								target.isoformat(),
								runtime["transit_days"],
								"forward" if direction > 0 else "backward",
							)

				if runtime["in_transit"]:
					if runtime.get("transit_days", 0) % 25 == 0:
						logging.info(
							"[%s] transit: skipping %s toward %s",
							name,
							candidate.isoformat(),
							runtime["transit_target"].isoformat() if runtime["transit_target"] else "?",
						)
					runtime["cursor"] = candidate
					continue

				if processed_budget_reached():
					continue

				if not reprocess and is_day_fully_processed(conn, files):
					runtime["cursor"] = candidate
					continue

				if not context.take_claim(candidate, name):
					logging.info(
						"[%s] day %s already claimed by another lane — skipping",
						name,
						candidate.isoformat(),
					)
					runtime["cursor"] = candidate
					continue

				batch_ok = 0
				for file in files:
					if stop.is_set() or processed_budget_reached():
						break
					if not reprocess:
						stats = get_sitemap_completion_stats(conn, [file.loc])
						if stats.get(file.loc) is not None and (
							stats[file.loc][0] == stats[file.loc][1] + stats[file.loc][2]
						):
							continue
					governor.acquire()
					try:
						xml_payload = fetch_xml(
							file.loc,
							timeout_seconds=timeout_seconds,
							max_attempts=max_attempts,
							base_cooldown_seconds=sitemap_base_cooldown_seconds,
							jitter_seconds=sitemap_jitter_seconds,
						)
					except urllib.error.HTTPError as exc:
						governor.on_signal(exc.code, detail="daily sitemap fetch")
						break
					except (urllib.error.URLError, TimeoutError) as exc:
						governor.on_signal(None, detail="daily sitemap fetch")
						break
					governor.on_success()
					file_counts = process_sitemap_file(
						conn=conn,
						sitemap=file,
						xml_payload=xml_payload,
						target_date=candidate,
						reprocess=reprocess,
						max_articles_per_sitemap=max_articles_per_sitemap,
						dry_run=dry_run,
						concurrency=concurrency,
						governor=governor,
						category=f"[{name}]",
						timeout_seconds=timeout_seconds,
						max_attempts=max_attempts,
						article_base_cooldown_seconds=article_base_cooldown_seconds,
						article_jitter_seconds=article_jitter_seconds,
					)
					note_processed_file(1)
					batch_ok += file_counts["ok"]
				context.release_claim(candidate, name)
				runtime["cursor"] = candidate

			logging.info(
				"[%s] lane finished (steps=%d, cursor=%s)",
				name,
				runtime["steps"],
				runtime["cursor"].isoformat(),
			)

	threads = []
	for index, runtime in enumerate(context.runtimes.values(), start=1):
		thread = threading.Thread(target=lane_loop, args=(runtime, index), name=runtime["lane"].name)
		thread.start()
		threads.append(thread)
	for thread in threads:
		thread.join()
	logging.info("Rate governor final state: %s", governor.state())
	logging.info(
		"Lanes sweep done. lanes=%d files_processed=%d dry_run=%s",
		len(input_lanes),
		done_files[0],
		dry_run,
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
	start_rps: float = 0.3,
	min_rps: float = 0.15,
	max_rps: float = 3.0,
	fixed_rate: bool = False,
	concurrency: int = 4,
) -> None:
	with psycopg.connect(db_dsn) as conn:
		ensure_tracking_tables(conn)

		governor = RateGovernor(
			start_rps=start_rps,
			min_rps=min_rps,
			max_rps=max_rps,
			fixed=fixed_rate,
		)

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
			governor.acquire()
			try:
				xml_payload = fetch_xml(
					sitemap.loc,
					timeout_seconds=timeout_seconds,
					max_attempts=max_attempts,
					base_cooldown_seconds=sitemap_base_cooldown_seconds,
					jitter_seconds=sitemap_jitter_seconds,
				)
			except urllib.error.HTTPError as exc:
				governor.on_signal(exc.code, detail="sitemap fetch")
				raise
			except (urllib.error.URLError, TimeoutError) as exc:
				governor.on_signal(None, detail="sitemap fetch")
				raise
			governor.on_success()
			file_counts = process_sitemap_file(
				conn=conn,
				sitemap=sitemap,
				xml_payload=xml_payload,
				target_date=target_date,
				reprocess=reprocess,
				max_articles_per_sitemap=max_articles_per_sitemap,
				dry_run=dry_run,
				concurrency=concurrency,
				governor=governor,
				category=f"[{i}/{len(daily_sitemaps)}]",
				timeout_seconds=timeout_seconds,
				max_attempts=max_attempts,
				article_base_cooldown_seconds=article_base_cooldown_seconds,
				article_jitter_seconds=article_jitter_seconds,
			)
			total_urls_seen += file_counts["urls"]
			total_ok += file_counts["ok"]
			total_failed += file_counts["failed"]

		logging.info("Rate governor final state: %s", governor.state())

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
		help="Retry backoff base for failed sitemap requests (steady pacing is adaptive now).",
	)
	parser.add_argument(
		"--sitemap-jitter-seconds",
		type=float,
		default=2.8,
		help="Jitter added to sitemap retry backoff.",
	)
	parser.add_argument(
		"--article-base-cooldown-seconds",
		type=float,
		default=2.0,
		help="Retry backoff base for failed article requests (steady pacing is adaptive now).",
	)
	parser.add_argument(
		"--article-jitter-seconds",
		type=float,
		default=1.0,
		help="Jitter added to article retry backoff.",
	)
	parser.add_argument(
		"--concurrency",
		type=int,
		default=4,
		help="Worker threads fetching articles in parallel; aggregate pace is still governed by --rps (1 = serial).",
	)
	parser.add_argument(
		"--rps",
		type=float,
		default=0.3,
		help="Starting aggregate request rate (req/s; ~0.3 reproduces the legacy serial pacing). The governor ramps up while the edge stays clean.",
	)
	parser.add_argument(
		"--min-rps",
		type=float,
		default=0.15,
		help="Floor the governor never goes below when throttled (req/s).",
	)
	parser.add_argument(
		"--max-rps",
		type=float,
		default=3.0,
		help="Absolute rate ceiling of the probe (req/s). Raise it on clean probes once you have a baseline.",
	)
	parser.add_argument(
		"--fixed-rate",
		action="store_true",
		help="Hold --rps constant (disables the ramp; penalty pauses on throttle signals still apply).",
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
	parser.add_argument(
		"--lanes",
		type=str,
		default=None,
		help=(
			"Multi-directional date sweep (replaces the newest-first list walk). Comma list of "
			"'YYYY-MM-DD[:forward|backward]' items, e.g. --lanes \"2026-03-31:backward,2026-10-06:forward\". "
			"Lanes step day by day in their direction over cached month listings; when a lane hits a "
			"boundary (beyond today or an empty/unavailable month) it flips direction and walks to the "
			"other lane's current date before continuing. Fully processed days are skipped, not refetched."
		),
	)
	parser.add_argument(
		"--max-lane-steps",
		type=int,
		default=100000,
		help="Safety cap of day-steps per lane in --lanes mode (scanning passes over processed days also consume steps). The full archive spans ~8.7k days from 2003.",
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

	governor_defaults = dict(
		timeout_seconds=max(5, args.timeout_seconds),
		max_attempts=max(1, args.max_attempts),
		sitemap_base_cooldown_seconds=max(0.0, args.sitemap_base_cooldown_seconds),
		sitemap_jitter_seconds=max(0.0, args.sitemap_jitter_seconds),
		article_base_cooldown_seconds=max(0.0, args.article_base_cooldown_seconds),
		article_jitter_seconds=max(0.0, args.article_jitter_seconds),
		start_rps=max(0.01, args.rps),
		min_rps=max(0.01, args.min_rps),
		max_rps=max(max(0.01, args.min_rps), args.max_rps),
		fixed_rate=args.fixed_rate,
		concurrency=max(1, args.concurrency),
	)

	if args.lanes:
		if args.backward_from is not None:
			logging.warning("--backward-from is ignored in --lanes mode (lanes define their own directions).")
		try:
			lanes = parse_lane_spec(args.lanes)
		except ValueError as exc:
			raise SystemExit(str(exc)) from exc
		governor = RateGovernor(
			start_rps=governor_defaults["start_rps"],
			min_rps=governor_defaults["min_rps"],
			max_rps=governor_defaults["max_rps"],
			fixed=governor_defaults["fixed_rate"],
		)
		run_lanes(
			db_dsn=args.db_dsn,
			lanes=lanes,
			sitemap_root=args.sitemap_root,
			governor=governor,
			timeout_seconds=governor_defaults["timeout_seconds"],
			max_attempts=governor_defaults["max_attempts"],
			sitemap_base_cooldown_seconds=governor_defaults["sitemap_base_cooldown_seconds"],
			sitemap_jitter_seconds=governor_defaults["sitemap_jitter_seconds"],
			article_base_cooldown_seconds=governor_defaults["article_base_cooldown_seconds"],
			article_jitter_seconds=governor_defaults["article_jitter_seconds"],
			max_articles_per_sitemap=args.max_articles_per_sitemap,
			dry_run=args.dry_run,
			reprocess=args.reprocess,
			max_sitemaps=args.max_sitemaps,
			max_lane_steps=max(1, args.max_lane_steps),
			concurrency=governor_defaults["concurrency"],
		)
		return

	run(
		db_dsn=args.db_dsn,
		target_date=target_date,
		index_url=args.index_url,
		sitemap_root=args.sitemap_root,
		max_sitemaps=args.max_sitemaps,
		max_articles_per_sitemap=args.max_articles_per_sitemap,
		dry_run=args.dry_run,
		reprocess=args.reprocess,
		backward_from=args.backward_from,
		**governor_defaults,
	)


if __name__ == "__main__":
	main()
