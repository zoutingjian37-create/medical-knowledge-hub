"""Resolve legal open full text through small, ordered public-source adapters."""

from dataclasses import replace
import os
import re
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx

from .discovery import LiteratureItem, validate_public_http_url


EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
_ARXIV_ABS = re.compile(r"^/abs/([^/?#]+)$", re.IGNORECASE)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)


class FullTextResolverChain:
    """Stop at the first provider that supplies a PDF URL."""

    def __init__(self, resolvers=None, *, client=None, email=None, resolver=None):
        if resolvers is None:
            shared_client = client or httpx.AsyncClient()
            contact = (
                os.getenv("CONTENT_HUB_UNPAYWALL_EMAIL", "")
                if email is None
                else email
            )
            resolvers = (
                EuropePMCFullTextResolver(client=shared_client),
                UnpaywallFullTextResolver(client=shared_client, email=contact),
                PreprintFullTextResolver(),
                CitationMetaFullTextResolver(
                    client=shared_client,
                    resolver=resolver,
                ),
            )
        self.resolvers = tuple(resolvers)

    async def resolve(self, item: LiteratureItem, skip_urls=()) -> LiteratureItem:
        skipped = {str(url).strip() for url in skip_urls if str(url).strip()}
        if item.pdf_url and item.pdf_url not in skipped:
            return item
        current = (
            replace(item, pdf_url="", pdf_source="")
            if item.pdf_url in skipped
            else item
        )
        for provider in self.resolvers:
            try:
                current = await provider.resolve(current)
            except (httpx.HTTPError, OSError, RuntimeError, ValueError):
                continue
            if current.pdf_url:
                if current.pdf_url in skipped:
                    current = replace(current, pdf_url="", pdf_source="")
                    continue
                return current
        return current


class EuropePMCFullTextResolver:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient()

    async def resolve(self, item: LiteratureItem) -> LiteratureItem:
        query = _europe_pmc_identifier_query(item)
        if not query:
            return item
        response = await self.client.get(
            EUROPE_PMC_SEARCH,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": 1,
            },
            headers={"Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json().get("resultList", {}).get("result", [])
        if not rows:
            return item
        row = rows[0]
        full_text_urls = row.get("fullTextUrlList", {}).get("fullTextUrl", [])
        pdf_url = next(
            (
                str(entry.get("url") or "").strip()
                for entry in full_text_urls
                if str(entry.get("documentStyle") or "").casefold() == "pdf"
            ),
            "",
        )
        return replace(
            item,
            pmid=item.pmid or str(row.get("pmid") or "").strip(),
            pdf_url=pdf_url,
            open_access=item.open_access or bool(pdf_url),
            pdf_source="europe_pmc" if pdf_url else item.pdf_source,
        )


class UnpaywallFullTextResolver:
    def __init__(self, client=None, email=None):
        self.client = client or httpx.AsyncClient()
        self.email = str(email or "").strip()

    async def resolve(self, item: LiteratureItem) -> LiteratureItem:
        if not item.doi or not self.email:
            return item
        response = await self.client.get(
            f"{UNPAYWALL_API}/{quote(item.doi, safe='')}",
            params={"email": self.email},
            headers={
                "Accept": "application/json",
                "User-Agent": "MedicalKnowledgeHub/1.1",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        locations = [payload.get("best_oa_location") or {}]
        locations.extend(payload.get("oa_locations") or [])
        pdf_url = next(
            (
                str(location.get("url_for_pdf") or "").strip()
                for location in locations
                if str(location.get("url_for_pdf") or "").strip()
            ),
            "",
        )
        if not pdf_url:
            return item
        return replace(
            item,
            pdf_url=pdf_url,
            open_access=True,
            pdf_source="unpaywall",
        )


class PreprintFullTextResolver:
    async def resolve(self, item: LiteratureItem) -> LiteratureItem:
        parsed = urlsplit(item.url)
        hostname = parsed.hostname.casefold() if parsed.hostname else ""
        if hostname in {"arxiv.org", "www.arxiv.org"}:
            match = _ARXIV_ABS.match(parsed.path)
            if match:
                return replace(
                    item,
                    pdf_url=f"https://arxiv.org/pdf/{match.group(1)}",
                    open_access=True,
                    pdf_source="arxiv",
                )
        for source in ("medrxiv", "biorxiv"):
            if hostname in {f"{source}.org", f"www.{source}.org"}:
                path = parsed.path.rstrip("/")
                if path.startswith("/content/10.1101/"):
                    return replace(
                        item,
                        pdf_url=f"https://www.{source}.org{path}.full.pdf",
                        open_access=True,
                        pdf_source=source,
                    )
        match = _ARXIV_DOI.match(item.doi)
        if match:
            return replace(
                item,
                pdf_url=f"https://arxiv.org/pdf/{match.group(1)}",
                open_access=True,
                pdf_source="arxiv",
            )
        return item


class CitationMetaFullTextResolver:
    def __init__(self, client=None, resolver=None):
        self.client = client or httpx.AsyncClient()
        self.resolver = resolver

    async def resolve(self, item: LiteratureItem) -> LiteratureItem:
        if not item.open_access or not item.url:
            return item
        current = item.url
        for _ in range(4):
            validate_public_http_url(current, resolver=self.resolver)
            response = await self.client.get(
                current,
                headers={"Accept": "text/html,application/xhtml+xml"},
                follow_redirects=False,
                timeout=20,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    return item
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            pdf_url = _citation_pdf_url(response.text, current)
            if not pdf_url:
                return item
            validate_public_http_url(pdf_url, resolver=self.resolver)
            return replace(
                item,
                pdf_url=pdf_url,
                pdf_source="citation_pdf_url",
            )
        return item


def _europe_pmc_identifier_query(item: LiteratureItem) -> str:
    if item.doi:
        return f'DOI:"{item.doi}"'
    if item.pmid:
        return f'EXT_ID:"{item.pmid}" AND SRC:MED'
    return ""


def _citation_pdf_url(document: str, base_url: str) -> str:
    soup = BeautifulSoup(document, "html.parser")
    for tag in soup.find_all("meta"):
        name = str(tag.get("name") or tag.get("property") or "").casefold()
        if name == "citation_pdf_url":
            content = str(tag.get("content") or "").strip()
            return urljoin(base_url, content) if content else ""
    return ""
