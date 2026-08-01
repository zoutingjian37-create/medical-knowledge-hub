"""Metadata completion through Crossref and OpenAlex public APIs."""

from dataclasses import replace
from urllib.parse import quote

from bs4 import BeautifulSoup
import httpx

from .discovery import LiteratureItem


class MetadataEnricher:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient()

    async def enrich(self, item: LiteratureItem) -> LiteratureItem:
        enriched = item
        if item.doi and (not item.title or not item.authors or not item.abstract):
            try:
                enriched = await self._crossref(enriched)
            except (httpx.HTTPError, RuntimeError, ValueError):
                pass
        if enriched.doi and (not enriched.openalex_id or not enriched.pdf_url):
            try:
                enriched = await self._openalex(enriched)
            except (httpx.HTTPError, RuntimeError, ValueError):
                pass
        return enriched

    async def _crossref(self, item: LiteratureItem) -> LiteratureItem:
        response = await self.client.get(
            f"https://api.crossref.org/works/{quote(item.doi, safe='')}",
            headers={"Accept": "application/json", "User-Agent": "MedicalKnowledgeHub/1.1"},
            timeout=20,
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        authors = "; ".join(
            " ".join(
                value
                for value in (str(author.get("given") or "").strip(), str(author.get("family") or "").strip())
                if value
            )
            for author in message.get("author", [])
        )
        parts = message.get("published", {}).get("date-parts", [[]])[0]
        published = "-".join(str(value) for value in parts)
        abstract = BeautifulSoup(str(message.get("abstract") or ""), "html.parser").get_text(" ", strip=True)
        titles = message.get("title", [])
        return replace(
            item,
            title=item.title or (str(titles[0]).strip() if titles else ""),
            authors=item.authors or authors,
            abstract=item.abstract or abstract,
            published_at=item.published_at or published,
            url=item.url or str(message.get("URL") or "").strip(),
        )

    async def _openalex(self, item: LiteratureItem) -> LiteratureItem:
        response = await self.client.get(
            f"https://api.openalex.org/works/https://doi.org/{quote(item.doi, safe='')}",
            headers={"Accept": "application/json", "User-Agent": "MedicalKnowledgeHub/1.1"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        location = payload.get("best_oa_location") or {}
        identifier = str(payload.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
        return replace(
            item,
            openalex_id=item.openalex_id or identifier,
            pdf_url=item.pdf_url or str(location.get("pdf_url") or "").strip(),
            open_access=item.open_access or bool(payload.get("open_access", {}).get("is_oa")),
        )
