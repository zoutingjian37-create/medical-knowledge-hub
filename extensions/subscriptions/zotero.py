"""Narrow Zotero connector boundary for user-authorized local imports."""

import asyncio
import json
import re
from uuid import uuid4
from urllib.parse import urljoin

import httpx

from .discovery import LiteratureItem, validate_public_http_url


DEFAULT_ZOTERO_URL = "http://127.0.0.1:23119"
MAX_PDF_BYTES = 50 * 1024 * 1024


class SchoolLoginRequired(RuntimeError):
    """The remote PDF endpoint requires the user's browser login."""


class ZoteroGateway:
    def __init__(
        self,
        client=None,
        base_url: str = DEFAULT_ZOTERO_URL,
        resolver=None,
        sleep=asyncio.sleep,
        fulltext=None,
    ):
        self._client = client or httpx.AsyncClient()
        self._base_url = base_url.rstrip("/")
        self._resolver = resolver
        self._sleep = sleep
        self._fulltext = fulltext

    async def status(self) -> dict:
        try:
            api = await self._client.get(f"{self._base_url}/api/", timeout=3)
            connector = await self._client.post(
                f"{self._base_url}/connector/ping",
                json={},
                headers=_connector_headers(),
                timeout=3,
            )
        except (httpx.HTTPError, OSError) as exc:
            return {"ready": False, "detail": f"Zotero is not reachable: {exc}"}
        return {
            "ready": api.status_code < 400 and connector.status_code < 400,
            "api": api.status_code,
            "connector": connector.status_code,
        }

    async def selected_collection(self) -> dict:
        response = await self._client.post(
            f"{self._base_url}/connector/getSelectedCollection",
            json={},
            headers=_connector_headers(),
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    async def save(self, item: LiteratureItem, collection: str) -> dict:
        if not item.open_access:
            return {
                "status": "waiting_school_login",
                "url": item.url,
                "doi": item.doi,
            }
        try:
            selected = await self.selected_collection()
        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            return {"status": "zotero_unavailable", "detail": str(exc)}
        selected_name = str(selected.get("name") or selected.get("collectionName") or "").strip()
        if selected_name != collection:
            return {
                "status": "waiting_collection",
                "expected_collection": collection,
                "selected_collection": selected_name,
            }

        session = f"medical-knowledge-hub-{uuid4().hex}"
        connector_item_id = f"mkh-{uuid4().hex}"
        connector_item = to_connector_item(item, connector_item_id)
        pdf_content = None
        resolved_pdf_url = ""
        pdf_error = ""
        pdf_source = ""
        attempted_urls = set()
        login_error = ""
        candidate = item
        while candidate.pdf_url and len(attempted_urls) < 6:
            attempted_urls.add(candidate.pdf_url)
            try:
                pdf_content, resolved_pdf_url = await self._download_pdf(
                    candidate.pdf_url
                )
                pdf_source = candidate.pdf_source
                break
            except SchoolLoginRequired as exc:
                login_error = _error_text(exc)
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                pdf_error = _error_text(exc)
            if self._fulltext is None:
                break
            try:
                candidate = await self._fulltext.resolve(
                    item, skip_urls=attempted_urls
                )
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                pdf_error = _error_text(exc)
                break
            if not candidate.pdf_url or candidate.pdf_url in attempted_urls:
                break
        if pdf_content is None and login_error:
            return {
                "status": "waiting_school_login",
                "url": item.url,
                "doi": item.doi,
                "pdf_error": login_error,
            }
        try:
            response = await self._client.post(
                f"{self._base_url}/connector/saveItems",
                json={
                    "sessionID": session,
                    "uri": item.url,
                    "items": [connector_item],
                },
                headers=_connector_headers(),
                timeout=20,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            return {"status": "zotero_unavailable", "detail": str(exc)}

        pdf_saved = False
        if pdf_content is not None:
            try:
                metadata = {
                    "sessionID": session,
                    "parentItemID": connector_item_id,
                    "title": _pdf_title(item),
                    "url": resolved_pdf_url,
                }
                attachment = await self._client.post(
                    f"{self._base_url}/connector/saveAttachment?sessionID={session}",
                    content=pdf_content,
                    headers={
                        **_connector_headers(),
                        "Content-Type": "application/pdf",
                        "Content-Length": str(len(pdf_content)),
                        "X-Metadata": json.dumps(metadata, ensure_ascii=False),
                    },
                    timeout=90,
                )
                attachment.raise_for_status()
                pdf_saved = True
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                pdf_error = _error_text(exc)

        item_key = await self.find_item_key(item)
        if item_key and pdf_saved:
            full_text = await self.wait_for_full_text(item_key)
        else:
            full_text = await self.read_full_text(item_key) if item_key else ""
        return {
            "status": "saved",
            "item_key": item_key,
            "collection": collection,
            "full_text": full_text,
            "pdf_saved": pdf_saved,
            "pdf_error": pdf_error,
            "pdf_source": pdf_source,
        }

    async def _download_pdf(self, url: str) -> tuple[bytes, str]:
        current = str(url).strip()
        for _ in range(4):
            validate_public_http_url(
                current,
                resolver=self._resolver,
                allow_benchmark_proxy=True,
            )
            response = await self._client.get(
                current,
                headers={"Accept": "application/pdf"},
                follow_redirects=False,
                timeout=90,
            )
            if response.status_code in {401, 403}:
                raise SchoolLoginRequired(
                    f"PDF requires browser or school login (HTTP {response.status_code})"
                )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise RuntimeError("PDF redirect has no location")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content = bytes(response.content)
            declared = int(response.headers.get("content-length") or len(content))
            if declared > MAX_PDF_BYTES or len(content) > MAX_PDF_BYTES:
                raise RuntimeError("PDF exceeds the 50 MB safety limit")
            content_type = str(response.headers.get("content-type") or "").casefold()
            if "application/pdf" not in content_type and not content.startswith(b"%PDF-"):
                raise RuntimeError("open-access attachment is not a PDF")
            return content, current
        raise RuntimeError("PDF redirected too many times")

    async def contains(self, item: LiteratureItem) -> bool:
        return bool(await self.find_item_key(item))

    async def find_item_key(self, item: LiteratureItem) -> str:
        query = item.doi or item.pmid or item.title
        try:
            response = await self._client.get(
                f"{self._base_url}/api/users/0/items",
                params={"q": query, "qmode": "everything", "limit": 10},
                headers={"Zotero-API-Version": "3"},
                timeout=5,
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, OSError, RuntimeError, ValueError):
            return ""
        needle = item.doi.casefold()
        if not needle:
            row = rows[0] if rows and isinstance(rows[0], dict) else {}
            return str(row.get("key") or row.get("data", {}).get("key") or "")
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("data", {}).get("DOI") or "").casefold() == needle:
                return str(row.get("key") or row.get("data", {}).get("key") or "")
        return ""

    async def read_full_text(self, item_key: str) -> str:
        try:
            children = await self._client.get(
                f"{self._base_url}/api/users/0/items/{item_key}/children",
                headers={"Zotero-API-Version": "3"},
                timeout=5,
            )
            children.raise_for_status()
            rows = children.json()
            if not isinstance(rows, list):
                return ""
            for row in rows:
                data = row.get("data", {}) if isinstance(row, dict) else {}
                if data.get("itemType") != "attachment":
                    continue
                key = str(row.get("key") or data.get("key") or "")
                if not key:
                    continue
                response = await self._client.get(
                    f"{self._base_url}/api/users/0/items/{key}/fulltext",
                    headers={"Zotero-API-Version": "3"},
                    timeout=8,
                )
                if response.status_code >= 400:
                    continue
                payload = response.json()
                content = str(payload.get("content") or "").strip()
                if content:
                    return content
        except (httpx.HTTPError, OSError, RuntimeError, ValueError):
            return ""
        return ""

    async def wait_for_full_text(self, item_key: str, attempts: int = 5) -> str:
        for attempt in range(max(1, attempts)):
            content = await self.read_full_text(item_key)
            if content:
                return content
            if attempt + 1 < attempts:
                await self._sleep(2)
        return ""



def to_connector_item(item: LiteratureItem, connector_item_id: str) -> dict:
    creators = []
    for value in re.split(r"\s*(?:;|\band\b)\s*", item.authors):
        name = value.strip()
        if not name:
            continue
        parts = name.rsplit(" ", 1)
        creators.append(
            {
                "creatorType": "author",
                "firstName": parts[0] if len(parts) == 2 else "",
                "lastName": parts[-1],
            }
        )
    return {
        "id": connector_item_id,
        "itemType": "journalArticle",
        "title": item.title,
        "creators": creators,
        "date": item.published_at[:10],
        "DOI": item.doi,
        "abstractNote": item.abstract,
        "url": item.url,
        "tags": [],
    }


def _connector_headers() -> dict:
    return {"X-Zotero-Connector-API-Version": "3"}


def _pdf_title(item: LiteratureItem) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", " ", item.title, flags=re.UNICODE).strip()
    return f"{cleaned[:120] or 'Full text'}.pdf"


def _error_text(error: Exception) -> str:
    return str(error).strip() or type(error).__name__
