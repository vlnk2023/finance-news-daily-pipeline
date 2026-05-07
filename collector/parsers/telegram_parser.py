"""Parser for Telegram public static channel pages.

Telegram channel URLs intended for apps, such as https://t.me/FinanceNewsDaily,
do not expose the message HTML we need. Use the public static page instead:
https://t.me/s/FinanceNewsDaily
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup


HTTP_URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
MESSAGE_ID_RE = re.compile(r"/(\d+)(?:\?.*)?$")


class TelegramParser:
    """Parse Telegram static public channel HTML into normalized items."""

    def parse(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []

        for message in soup.select("div.tgme_widget_message_wrap"):
            text_node = message.select_one("div.tgme_widget_message_text")
            date_link = message.select_one("a.tgme_widget_message_date[href]")
            time_node = message.select_one("time[datetime]")

            if not date_link:
                continue

            message_url = date_link.get("href", "").strip()
            raw_text = self._extract_text(text_node)
            preview_title = self._extract_text(
                message.select_one(".tgme_widget_message_link_preview_title")
            )
            title = self._select_title(raw_text, preview_title)
            external_urls = self._external_urls(text_node)

            items.append(
                {
                    "title": title,
                    "url": message_url,
                    "summary": raw_text,
                    "pub_str": time_node.get("datetime", "").strip()
                    if time_node
                    else "",
                    "guid": self._message_id(message_url),
                    "external_url": external_urls[0] if external_urls else "",
                    "external_urls": external_urls,
                    "preview_title": preview_title,
                    "raw_text_full": raw_text,
                }
            )

        return items

    def _extract_text(self, node: Any | None) -> str:
        if node is None:
            return ""

        html = str(node)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        lines = [line.strip() for line in unescape(text).splitlines()]
        return "\n".join(line for line in lines if line)

    def _select_title(self, raw_text: str, preview_title: str) -> str:
        first_line = next((line.strip() for line in raw_text.splitlines() if line.strip()), "")
        title = first_line or preview_title or "Untitled Telegram message"
        return self._clean_title(title)

    def _clean_title(self, title: str) -> str:
        title = title.strip()
        if title.startswith("〖") and title.endswith("〗") and len(title) > 2:
            return title[1:-1].strip()
        return title

    def _message_id(self, message_url: str) -> str:
        match = MESSAGE_ID_RE.search(message_url)
        return match.group(1) if match else ""

    def _external_urls(self, text_node: Any | None) -> list[str]:
        if text_node is None:
            return []

        urls: list[str] = []
        for link in text_node.select("a[href]"):
            href = link.get("href", "").strip()
            if self._is_external_http_url(href):
                urls.append(href)

        raw_text = self._extract_text(text_node)
        for match in HTTP_URL_RE.finditer(raw_text):
            url = match.group(0).rstrip(".,;:!?)，。；：！？）")
            if self._is_external_http_url(url):
                urls.append(url)

        return self._dedupe_preserve_order(urls)

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            unique_values.append(value)
        return unique_values

    def _is_external_http_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = parsed.netloc.lower()
        return host not in {"t.me", "telegram.me"} and not host.endswith(".t.me")
