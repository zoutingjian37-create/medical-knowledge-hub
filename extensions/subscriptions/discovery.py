"""Standards-based feed and biomedical literature discovery."""

from dataclasses import dataclass
import html
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import httpx

from .models import Subscription


EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_PMID = re.compile(r"(?:PMID\s*:?\s*)(\d{5,10})", re.IGNORECASE)
_OPENALEX = re.compile(r"(?:openalex\.org/)?(W\d+)", re.IGNORECASE)
_TRACKING_KEYS = {"ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid"}


class UnsafeFeedUrl(ValueError):
    """A feed target could reach a non-public network address."""


@dataclass(frozen=True)
class LiteratureItem:
    title: str
    url: str
    abstract: str = ""
    authors: str = ""
    published_at: str = ""
    doi: str = ""
    pmid: str = ""
    openalex_id: str = ""
    pdf_url: str = ""
    open_access: bool = False

    @property
    def identity_keys(self) -> tuple[str, ...]:
        values = []
        if self.doi:
            values.append(f"doi:{self.doi.casefold()}")
        if self.pmid:
            values.append(f"pmid:{self.pmid}")
        if self.openalex_id:
            values.append(f"openalex:{self.openalex_id.casefold()}")
        if self.url:
            values.append(f"url:{normalize_public_url(self.url)}")
        return tuple(values)


class FeedClient:
    def __init__(self, client=None, resolver=None):
        self._client = client or httpx.AsyncClient()
        self._resolver = resolver or socket.getaddrinfo

    async def fetch(self, url: str) -> tuple[LiteratureItem, ...]:
        current = str(url).strip()
        for _ in range(4):
            validate_public_http_url(current, resolver=self._resolver)
            response = await self._client.get(
                current,
                headers={"Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"},
                follow_redirects=False,
                timeout=30,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise RuntimeError("feed redirect has no location")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            try:
                return parse_feed(response.text)
            except ValueError:
                feed_url = _feed_url_from_html(response.text, current)
                if not feed_url:
                    raise
                current = feed_url
        raise RuntimeError("feed redirected too many times")


class EuropePMCClient:
    def __init__(self, client=None):
        self._client = client or httpx.AsyncClient()

    async def discover(self, subscription: Subscription) -> tuple[LiteratureItem, ...]:
        query = build_literature_query(subscription)
        response = await self._client.get(
            EUROPE_PMC_SEARCH,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": subscription.daily_limit,
                "sort": "P_PDATE_D desc",
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json().get("resultList", {}).get("result", [])
        return tuple(_from_europe_pmc(row) for row in rows)


class DefaultLiteratureDiscoverer:
    """Use a declared feed first and Europe PMC for structured queries."""

    def __init__(self, feed=None, europe_pmc=None, enricher=None):
        self.feed = feed or FeedClient()
        self.europe_pmc = europe_pmc or EuropePMCClient()
        if enricher is None:
            from .enrichment import MetadataEnricher

            enricher = MetadataEnricher()
        self.enricher = enricher

    async def discover(self, subscription: Subscription) -> tuple[LiteratureItem, ...]:
        if subscription.source.startswith(("http://", "https://")):
            try:
                items = await self.feed.fetch(subscription.source)
            except (ValueError, RuntimeError):
                if subscription.kind != "journal":
                    raise
                items = await self.europe_pmc.discover(subscription)
        else:
            items = await self.europe_pmc.discover(subscription)
        return tuple([await self.enricher.enrich(item) for item in items])


def build_literature_query(subscription: Subscription) -> str:
    parts = []
    if subscription.kind == "journal" and subscription.name:
        if re.fullmatch(r"\d{4}-[\dXx]{4}", subscription.source):
            parts.append(f'ISSN:"{subscription.source.upper()}"')
        else:
            parts.append(f'JOURNAL:"{subscription.name}"')
    if subscription.query:
        parts.append(f"({subscription.query})")
    parts.extend(f'("{keyword}")' for keyword in subscription.keywords)
    return " AND ".join(parts) or subscription.name


def parse_feed(xml: str) -> tuple[LiteratureItem, ...]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("invalid RSS or Atom document") from exc

    entries = [node for node in root.iter() if _local(node.tag) in {"item", "entry"}]
    items = []
    for entry in entries:
        fields: dict[str, list[str]] = {}
        links = []
        for child in list(entry):
            name = _local(child.tag)
            text = "".join(child.itertext()).strip()
            if text:
                fields.setdefault(name, []).append(text)
            if name == "link":
                href = str(child.attrib.get("href", "")).strip()
                relation = str(child.attrib.get("rel", "alternate"))
                if href and relation in {"alternate", ""}:
                    links.append(href)
                elif text:
                    links.append(text)
        title = _first(fields, "title") or "Untitled literature item"
        identifier_text = " ".join(
            value for values in fields.values() for value in values
        )
        url = links[0] if links else _first(fields, "link")
        if not url:
            identifier = _first(fields, "id", "guid")
            url = identifier if identifier.startswith(("http://", "https://")) else ""
        doi = _extract_doi(identifier_text)
        pmid_match = _PMID.search(identifier_text)
        openalex_match = _OPENALEX.search(identifier_text)
        items.append(
            LiteratureItem(
                title=title,
                url=normalize_public_url(url) if url else (f"https://doi.org/{doi}" if doi else ""),
                abstract=_first(fields, "description", "summary", "content"),
                authors=_first(fields, "author", "creator"),
                published_at=_first(fields, "pubDate", "published", "updated", "date"),
                doi=doi,
                pmid=pmid_match.group(1) if pmid_match else "",
                openalex_id=openalex_match.group(1).upper() if openalex_match else "",
            )
        )
    return tuple(items)


def validate_public_http_url(
    url: str, resolver=None, *, allow_benchmark_proxy: bool = False
) -> None:
    parsed = urlsplit(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeFeedUrl("feed URL must use public HTTP or HTTPS")
    hostname = parsed.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise UnsafeFeedUrl("feed URL cannot use a local host")
    try:
        direct = ipaddress.ip_address(hostname)
        addresses = [direct]
        hostname_is_ip = True
    except ValueError:
        hostname_is_ip = False
        lookup = resolver or socket.getaddrinfo
        try:
            addresses = {
                ipaddress.ip_address(row[4][0])
                for row in lookup(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            }
        except OSError as exc:
            raise UnsafeFeedUrl("feed host could not be resolved") from exc
    proxy_network = ipaddress.ip_network("198.18.0.0/15")
    proxy_fake_ip = (
        allow_benchmark_proxy
        and not hostname_is_ip
        and bool(addresses)
        and all(address in proxy_network for address in addresses)
    )
    if not addresses or (
        any(not address.is_global for address in addresses) and not proxy_fake_ip
    ):
        raise UnsafeFeedUrl("feed URL resolved to a non-public address")


def normalize_public_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_KEYS
    ]
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, urlencode(query), ""))


def _from_europe_pmc(row: dict) -> LiteratureItem:
    doi = str(row.get("doi") or "").strip().casefold()
    pmid = str(row.get("pmid") or "").strip()
    url = f"https://doi.org/{doi}" if doi else (
        f"https://europepmc.org/article/MED/{pmid}" if pmid else ""
    )
    full_text_urls = row.get("fullTextUrlList", {}).get("fullTextUrl", [])
    pdf_url = next(
        (
            str(entry.get("url") or "").strip()
            for entry in full_text_urls
            if str(entry.get("documentStyle") or "").casefold() == "pdf"
        ),
        "",
    )
    return LiteratureItem(
        title=_plain_text(row.get("title") or "Untitled literature item"),
        url=url,
        abstract=_plain_text(row.get("abstractText") or ""),
        authors=str(row.get("authorString") or "").strip(),
        published_at=str(row.get("firstPublicationDate") or row.get("electronicPublicationDate") or ""),
        doi=doi,
        pmid=pmid,
        openalex_id=str(row.get("openAlexId") or "").strip(),
        pdf_url=pdf_url,
        open_access=str(row.get("isOpenAccess") or "").upper() == "Y",
    )


def _extract_doi(value: str) -> str:
    match = _DOI.search(value)
    return match.group(0).rstrip(".,;)").casefold() if match else ""


def _first(fields: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = fields.get(name, [])
        if values:
            return values[0]
    return ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _feed_url_from_html(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link", href=True):
        relations = {str(value).casefold() for value in (link.get("rel") or [])}
        content_type = str(link.get("type") or "").casefold()
        if "alternate" in relations and ("rss" in content_type or "atom" in content_type):
            return urljoin(base_url, str(link["href"]))
    return ""


def _plain_text(value) -> str:
    decoded = html.unescape(str(value or ""))
    return BeautifulSoup(decoded, "html.parser").get_text(" ", strip=True)
