"""Safe public web-page ingestion for Document AI.

Only HTTPS pages on explicitly allowlisted hosts are fetched. Redirects are disabled,
private/reserved IP destinations are rejected, robots.txt is respected, and response
size/time are bounded. This intentionally does not execute JavaScript or bypass access
controls, logins, paywalls, or anti-bot protections.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import socket
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


USER_AGENT = "BhoomiSetuDocumentAI/1.0"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 60_000
SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "form"}


class WebImportError(ValueError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        else:
            self.parts.append(text)


def _validate_destination(host: str):
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise WebImportError("The website host could not be resolved.") from exc
    if not addresses:
        raise WebImportError("The website host has no public address.")
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if not ip.is_global:
            raise WebImportError("Private, local, and reserved network destinations are blocked.")


def _robots_allows(origin: str, path: str) -> bool:
    robots_url = origin + "/robots.txt"
    try:
        response = httpx.get(robots_url, headers={"User-Agent": USER_AGENT},
                             timeout=8.0, follow_redirects=False)
        if response.status_code == 404:
            return True
        if response.status_code != 200 or len(response.content) > 512 * 1024:
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, origin + path)
    except httpx.HTTPError:
        return False


def fetch_public_page(url: str, allowed_domains: str) -> dict:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise WebImportError("Only public HTTPS webpage URLs are accepted.")
    host = parsed.hostname.lower().rstrip(".")
    allowed = {d.strip().lower().rstrip(".") for d in allowed_domains.split(",") if d.strip()}
    if host not in allowed:
        raise WebImportError("This website is not allowlisted by the administrator.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise WebImportError("The webpage URL contains an invalid port.") from exc
    if port not in (None, 443):
        raise WebImportError("Custom ports are not allowed.")
    _validate_destination(host)
    origin = f"https://{host}"
    if not _robots_allows(origin, parsed.path or "/"):
        raise WebImportError("robots.txt disallows this page or could not be checked.")
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                          timeout=15.0, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    raise WebImportError("Redirects are blocked. Import the final HTTPS URL directly.")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    raise WebImportError("The URL did not return an HTML webpage.")
                declared_size = response.headers.get("content-length")
                if declared_size and declared_size.isdigit() and int(declared_size) > MAX_RESPONSE_BYTES:
                    raise WebImportError("The webpage exceeds the 2 MB import limit.")
                chunks = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise WebImportError("The webpage exceeds the 2 MB import limit.")
                    chunks.append(chunk)
                html_bytes = b"".join(chunks)
                encoding = response.encoding or "utf-8"
                html = html_bytes.decode(encoding, errors="replace")
    except WebImportError:
        raise
    except httpx.HTTPError as exc:
        raise WebImportError("The webpage could not be fetched.") from exc

    parser = _TextExtractor()
    parser.feed(html)
    text = "\n".join(" ".join(part.split()) for part in parser.parts if part.strip())
    text = "\n".join(line for line in text.splitlines() if line).strip()[:MAX_TEXT_CHARS]
    if len(text) < 80:
        raise WebImportError("Not enough readable page text was found.")
    title = " ".join(parser.title_parts).strip() or host
    return {
        "title": title[:200],
        "text": text,
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
