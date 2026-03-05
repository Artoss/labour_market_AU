"""
HTTP download client for Australian labour market data files.
Synchronous httpx client with retry logic and polite delays.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from labour_market_au.config import HttpConfig

logger = logging.getLogger("labour_market_au.scraping.client")


class DownloadResult:
    """Result of a single file download."""

    def __init__(
        self,
        site: str,
        dataset_key: str,
        filename: str,
        url: str,
        filepath: Path,
        file_hash: str,
        file_size: int,
        skipped: bool = False,
    ):
        self.site = site
        self.dataset_key = dataset_key
        self.filename = filename
        self.url = url
        self.filepath = filepath
        self.file_hash = file_hash
        self.file_size = file_size
        self.skipped = skipped


class DownloadClient:
    """Synchronous HTTP client for downloading data files."""

    def __init__(self, config: HttpConfig, data_dir: str | Path = "data"):
        self.config = config
        self.data_dir = Path(data_dir)
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            headers=config.default_headers,
            follow_redirects=True,
        )
        self._last_request_time: float = 0

    def close(self) -> None:
        self._client.close()

    def _polite_delay(self) -> None:
        """Wait between requests to be polite."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(
            self.config.min_delay_seconds,
            self.config.max_delay_seconds,
        )
        remaining = delay - elapsed
        if remaining > 0:
            logger.debug("Polite delay: %.1fs", remaining)
            time.sleep(remaining)

    def _rotate_user_agent(self) -> dict[str, str]:
        """Pick a random user agent."""
        ua = random.choice(self.config.user_agents)
        return {"User-Agent": ua}

    @staticmethod
    def file_hash(filepath: Path) -> str:
        """SHA256 hash of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def fetch_page(self, url: str) -> str:
        """Fetch an HTML page and return the text content."""
        self._polite_delay()
        logger.info("Fetching page: %s", url)
        response = self._fetch_with_retry(url)
        self._last_request_time = time.time()
        return response.text

    def download_file(
        self,
        site: str,
        dataset: str,
        url: str,
        filename: str,
        known_hash: str | None = None,
    ) -> DownloadResult:
        """Download a single file. Skip if hash matches known_hash."""
        out_dir = self.data_dir / site / dataset
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / filename

        # Check existing file hash for incremental mode
        if known_hash and filepath.exists():
            existing_hash = self.file_hash(filepath)
            if existing_hash == known_hash:
                logger.info("Skipping %s (hash unchanged)", filename)
                return DownloadResult(
                    site=site,
                    dataset_key=dataset,
                    filename=filename,
                    url=url,
                    filepath=filepath,
                    file_hash=existing_hash,
                    file_size=filepath.stat().st_size,
                    skipped=True,
                )

        self._polite_delay()
        logger.info("Downloading %s from %s", filename, url)

        response = self._fetch_with_retry(url)
        filepath.write_bytes(response.content)
        self._last_request_time = time.time()

        fhash = self.file_hash(filepath)
        fsize = filepath.stat().st_size
        logger.info("Downloaded %s (%d bytes, hash=%s)", filename, fsize, fhash[:12])

        return DownloadResult(
            site=site,
            dataset_key=dataset,
            filename=filename,
            url=url,
            filepath=filepath,
            file_hash=fhash,
            file_size=fsize,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        reraise=True,
    )
    def _fetch_with_retry(self, url: str) -> httpx.Response:
        """Fetch URL with automatic retry on failure."""
        headers = self._rotate_user_agent()
        response = self._client.get(url, headers=headers)
        response.raise_for_status()
        return response

    def download_catalog_files(
        self,
        files: list,
        known_hashes: dict[str, str] | None = None,
    ) -> list[DownloadResult]:
        """Download a list of FileDataset entries, returning results."""
        known_hashes = known_hashes or {}
        results = []
        for fd in files:
            try:
                result = self.download_file(
                    site=fd.site,
                    dataset=fd.dataset,
                    url=fd.url,
                    filename=fd.filename,
                    known_hash=known_hashes.get(fd.filename),
                )
                results.append(result)
            except Exception as e:
                logger.error("Failed to download %s: %s", fd.filename, e)
        return results
