import asyncio
from dataclasses import replace
import unittest


class Response:
    def __init__(self, *, payload=None, text="", status_code=200, headers=None):
        self._payload = payload or {}
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.content = text.encode("utf-8")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FullTextResolverTests(unittest.TestCase):
    def test_chain_keeps_existing_pdf_without_calling_fallbacks(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import FullTextResolverChain

        class Resolver:
            async def resolve(self, item):
                raise AssertionError("fallback must not run when a PDF is already known")

        item = LiteratureItem(
            title="Known PDF",
            url="https://example.org/article",
            pdf_url="https://example.org/article.pdf",
            open_access=True,
            pdf_source="europe_pmc",
        )
        resolved = asyncio.run(FullTextResolverChain((Resolver(),)).resolve(item))

        self.assertIs(item, resolved)

    def test_chain_continues_after_a_provider_failure(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import FullTextResolverChain

        calls = []

        class Broken:
            async def resolve(self, item):
                calls.append("broken")
                raise RuntimeError("provider unavailable")

        class Working:
            async def resolve(self, item):
                calls.append("working")
                return replace(
                    item,
                    pdf_url="https://repository.example/paper.pdf",
                    open_access=True,
                    pdf_source="unpaywall",
                )

        item = LiteratureItem(title="Fallback", url="https://doi.org/10.1000/fallback")
        resolved = asyncio.run(
            FullTextResolverChain((Broken(), Working())).resolve(item)
        )

        self.assertEqual(["broken", "working"], calls)
        self.assertEqual("unpaywall", resolved.pdf_source)

    def test_chain_skips_a_pdf_url_that_already_failed_to_download(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import FullTextResolverChain

        failed = "https://europepmc.org/broken.pdf"

        class SameLocation:
            async def resolve(self, item):
                return replace(
                    item,
                    pdf_url=failed,
                    open_access=True,
                    pdf_source="europe_pmc",
                )

        class Alternative:
            async def resolve(self, item):
                return replace(
                    item,
                    pdf_url="https://repository.example/working.pdf",
                    open_access=True,
                    pdf_source="unpaywall",
                )

        item = LiteratureItem(
            title="Broken primary",
            url="https://doi.org/10.1000/retry",
            doi="10.1000/retry",
            pdf_url=failed,
            open_access=True,
            pdf_source="europe_pmc",
        )
        resolved = asyncio.run(
            FullTextResolverChain((SameLocation(), Alternative())).resolve(
                item, skip_urls={failed}
            )
        )

        self.assertEqual("https://repository.example/working.pdf", resolved.pdf_url)
        self.assertEqual("unpaywall", resolved.pdf_source)

    def test_europe_pmc_resolver_finds_an_open_pdf_by_doi(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import EuropePMCFullTextResolver

        class Transport:
            def __init__(self):
                self.params = None

            async def get(self, url, **kwargs):
                self.params = kwargs["params"]
                return Response(
                    payload={
                        "resultList": {
                            "result": [
                                {
                                    "pmid": "12345678",
                                    "isOpenAccess": "Y",
                                    "fullTextUrlList": {
                                        "fullTextUrl": [
                                            {
                                                "documentStyle": "pdf",
                                                "url": "https://europepmc.org/articles/PMC1/bin/paper.pdf",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                )

        transport = Transport()
        item = LiteratureItem(
            title="PMC fallback",
            url="https://doi.org/10.1000/pmc",
            doi="10.1000/pmc",
        )
        resolved = asyncio.run(
            EuropePMCFullTextResolver(client=transport).resolve(item)
        )

        self.assertEqual('DOI:"10.1000/pmc"', transport.params["query"])
        self.assertEqual("12345678", resolved.pmid)
        self.assertEqual("europe_pmc", resolved.pdf_source)
        self.assertTrue(resolved.open_access)

    def test_unpaywall_uses_best_open_access_pdf_and_identifies_itself(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import UnpaywallFullTextResolver

        class Transport:
            def __init__(self):
                self.params = None

            async def get(self, url, **kwargs):
                self.params = kwargs["params"]
                return Response(
                    payload={
                        "is_oa": True,
                        "best_oa_location": {
                            "url_for_pdf": "https://repository.example/open.pdf"
                        },
                    }
                )

        transport = Transport()
        item = LiteratureItem(
            title="Repository copy",
            url="https://doi.org/10.1000/open",
            doi="10.1000/open",
        )
        resolved = asyncio.run(
            UnpaywallFullTextResolver(
                client=transport, email="researcher@example.org"
            ).resolve(item)
        )

        self.assertEqual("researcher@example.org", transport.params["email"])
        self.assertEqual("https://repository.example/open.pdf", resolved.pdf_url)
        self.assertEqual("unpaywall", resolved.pdf_source)
        self.assertTrue(resolved.open_access)

    def test_unpaywall_without_contact_email_does_not_make_a_request(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import UnpaywallFullTextResolver

        class Transport:
            async def get(self, url, **kwargs):
                raise AssertionError("Unpaywall requires an explicit contact email")

        item = LiteratureItem(
            title="No configuration",
            url="https://doi.org/10.1000/no-email",
            doi="10.1000/no-email",
        )
        resolved = asyncio.run(
            UnpaywallFullTextResolver(client=Transport(), email="").resolve(item)
        )

        self.assertIs(item, resolved)

    def test_arxiv_abstract_url_is_mapped_to_the_official_pdf(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import PreprintFullTextResolver

        item = LiteratureItem(
            title="Preprint",
            url="https://arxiv.org/abs/2607.12345v2",
        )
        resolved = asyncio.run(PreprintFullTextResolver().resolve(item))

        self.assertEqual("https://arxiv.org/pdf/2607.12345v2", resolved.pdf_url)
        self.assertEqual("arxiv", resolved.pdf_source)
        self.assertTrue(resolved.open_access)

    def test_medrxiv_article_url_is_mapped_to_its_versioned_pdf(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import PreprintFullTextResolver

        item = LiteratureItem(
            title="Medical preprint",
            url=(
                "https://www.medrxiv.org/content/"
                "10.1101/2026.07.01.12345678v2"
            ),
            doi="10.1101/2026.07.01.12345678",
        )
        resolved = asyncio.run(PreprintFullTextResolver().resolve(item))

        self.assertEqual(
            "https://www.medrxiv.org/content/"
            "10.1101/2026.07.01.12345678v2.full.pdf",
            resolved.pdf_url,
        )
        self.assertEqual("medrxiv", resolved.pdf_source)
        self.assertTrue(resolved.open_access)

    def test_open_access_landing_page_can_supply_citation_pdf_url(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.fulltext import CitationMetaFullTextResolver

        class Transport:
            async def get(self, url, **kwargs):
                return Response(
                    text=(
                        '<html><head><meta name="citation_pdf_url" '
                        'content="/downloads/paper.pdf"></head></html>'
                    ),
                    headers={"content-type": "text/html; charset=utf-8"},
                )

        public_dns = lambda *args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ]
        item = LiteratureItem(
            title="Publisher OA",
            url="https://journal.example/article/1",
            open_access=True,
        )
        resolved = asyncio.run(
            CitationMetaFullTextResolver(
                client=Transport(), resolver=public_dns
            ).resolve(item)
        )

        self.assertEqual(
            "https://journal.example/downloads/paper.pdf", resolved.pdf_url
        )
        self.assertEqual("citation_pdf_url", resolved.pdf_source)

    def test_discoverer_resolves_full_text_after_metadata_enrichment(self):
        from extensions.subscriptions.discovery import (
            DefaultLiteratureDiscoverer,
            LiteratureItem,
        )
        from extensions.subscriptions.store import SubscriptionStore
        from pathlib import Path
        from tempfile import TemporaryDirectory

        class Feed:
            async def fetch(self, url):
                return (LiteratureItem(title="Pipeline", url="https://example.org/1"),)

        class Enricher:
            async def enrich(self, item):
                return replace(item, doi="10.1000/pipeline")

        class FullText:
            async def resolve(self, item):
                return replace(
                    item,
                    pdf_url="https://example.org/1.pdf",
                    open_access=True,
                    pdf_source="test",
                )

        with TemporaryDirectory() as directory:
            subscription = SubscriptionStore(Path(directory)).create(
                kind="feed",
                name="Example",
                source="https://example.org/feed.xml",
            )
            items = asyncio.run(
                DefaultLiteratureDiscoverer(
                    feed=Feed(), enricher=Enricher(), fulltext=FullText()
                ).discover(subscription)
            )

        self.assertEqual("10.1000/pipeline", items[0].doi)
        self.assertEqual("test", items[0].pdf_source)


class ZoteroAccessHandoffTests(unittest.TestCase):
    def test_failed_primary_pdf_uses_the_next_full_text_provider(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.zotero import ZoteroGateway

        primary = "https://europepmc.org/broken.pdf"
        alternative = "https://repository.example/working.pdf"

        class PdfResponse(Response):
            def __init__(self, status_code, content=b"", content_type=""):
                super().__init__(
                    status_code=status_code,
                    headers={"content-type": content_type},
                )
                self.content = content

        class Transport:
            def __init__(self):
                self.downloads = []
                self.posts = []

            async def post(self, url, **kwargs):
                self.posts.append(url)
                if url.endswith("/connector/getSelectedCollection"):
                    return Response(payload={"name": "Target"})
                return Response(status_code=201)

            async def get(self, url, **kwargs):
                if url == primary:
                    self.downloads.append(url)
                    return PdfResponse(500)
                if url == alternative:
                    self.downloads.append(url)
                    return PdfResponse(
                        200,
                        content=b"%PDF-1.7 fallback",
                        content_type="application/pdf",
                    )
                if url.endswith("/api/users/0/items"):
                    return Response(
                        payload=[
                            {
                                "key": "ITEM1",
                                "data": {"DOI": "10.1000/retry"},
                            }
                        ]
                    )
                return Response(payload=[])

        class Fallback:
            async def resolve(self, item, skip_urls=()):
                self.skipped = set(skip_urls)
                return replace(
                    item,
                    pdf_url=alternative,
                    pdf_source="unpaywall",
                    open_access=True,
                )

        transport = Transport()
        fallback = Fallback()
        public_dns = lambda *args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ]
        item = LiteratureItem(
            title="Retry PDF",
            url="https://doi.org/10.1000/retry",
            doi="10.1000/retry",
            pdf_url=primary,
            open_access=True,
            pdf_source="europe_pmc",
        )
        result = asyncio.run(
            ZoteroGateway(
                client=transport,
                resolver=public_dns,
                fulltext=fallback,
                sleep=lambda _seconds: asyncio.sleep(0),
            ).save(item, "Target")
        )

        self.assertEqual([primary, alternative], transport.downloads)
        self.assertEqual({primary}, fallback.skipped)
        self.assertEqual("saved", result["status"])
        self.assertTrue(result["pdf_saved"])

    def test_pdf_403_waits_for_school_login_before_creating_zotero_item(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.zotero import ZoteroGateway

        class Transport:
            def __init__(self):
                self.posts = []

            async def post(self, url, **kwargs):
                self.posts.append(url)
                if url.endswith("/connector/getSelectedCollection"):
                    return Response(payload={"name": "Target"})
                return Response(status_code=201)

            async def get(self, url, **kwargs):
                return Response(status_code=403)

        transport = Transport()
        public_dns = lambda *args: [
            (None, None, None, None, ("93.184.216.34", 443))
        ]
        item = LiteratureItem(
            title="Restricted PDF",
            url="https://publisher.example/article",
            doi="10.1000/restricted",
            pdf_url="https://publisher.example/article.pdf",
            open_access=True,
            pdf_source="citation_pdf_url",
        )
        result = asyncio.run(
            ZoteroGateway(client=transport, resolver=public_dns).save(item, "Target")
        )

        self.assertEqual("waiting_school_login", result["status"])
        self.assertEqual("https://publisher.example/article", result["url"])
        self.assertFalse(any(url.endswith("/connector/saveItems") for url in transport.posts))


if __name__ == "__main__":
    unittest.main()
