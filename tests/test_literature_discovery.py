import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Example Medical Journal</title>
    <item>
      <title>Causal forests in clinical research</title>
      <link>https://example.org/article/1?utm_source=rss</link>
      <guid>doi:10.1000/example.1</guid>
      <dc:identifier>PMID:12345678</dc:identifier>
      <description>Methods and main conclusion.</description>
      <pubDate>Fri, 01 Aug 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Feed</title>
  <entry>
    <title>Target trial emulation</title>
    <id>https://doi.org/10.1000/example.2</id>
    <link rel="alternate" href="https://example.org/article/2" />
    <summary>Abstract evidence.</summary>
    <updated>2026-08-01T09:00:00Z</updated>
  </entry>
</feed>"""


class FeedParsingTests(unittest.TestCase):
    def test_pdf_validation_allows_proxy_fake_ip_but_still_rejects_literal_private_ip(self):
        from extensions.subscriptions.discovery import (
            UnsafeFeedUrl,
            validate_public_http_url,
        )

        fake_ip_resolver = lambda *args: [
            (None, None, None, None, ("198.18.0.31", 443))
        ]
        validate_public_http_url(
            "https://europepmc.org/article.pdf",
            resolver=fake_ip_resolver,
            allow_benchmark_proxy=True,
        )
        with self.assertRaises(UnsafeFeedUrl):
            validate_public_http_url(
                "http://127.0.0.1/private.pdf",
                resolver=fake_ip_resolver,
                allow_benchmark_proxy=True,
            )

    def test_rss_and_atom_are_normalized_to_literature_items(self):
        from extensions.subscriptions.discovery import parse_feed

        rss_item = parse_feed(RSS)[0]
        atom_item = parse_feed(ATOM)[0]

        self.assertEqual("10.1000/example.1", rss_item.doi)
        self.assertEqual("12345678", rss_item.pmid)
        self.assertEqual("https://example.org/article/1", rss_item.url)
        self.assertEqual("10.1000/example.2", atom_item.doi)
        self.assertEqual("Abstract evidence.", atom_item.abstract)

    def test_private_and_loopback_feed_urls_are_rejected_before_fetch(self):
        from extensions.subscriptions.discovery import FeedClient, UnsafeFeedUrl

        class Transport:
            async def get(self, url, **kwargs):
                raise AssertionError("unsafe URL must not reach the network")

        client = FeedClient(client=Transport())
        for url in (
            "http://127.0.0.1/feed",
            "http://169.254.169.254/latest/meta-data",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeFeedUrl):
                asyncio.run(client.fetch(url))

    def test_journal_homepage_discovers_declared_rss_or_atom_feed(self):
        from extensions.subscriptions.discovery import FeedClient

        class Response:
            status_code = 200
            headers = {}

            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class Transport:
            def __init__(self):
                self.urls = []

            async def get(self, url, **kwargs):
                self.urls.append(url)
                if len(self.urls) == 1:
                    return Response(
                        '<html><head><link rel="alternate" type="application/rss+xml" href="/latest.xml"></head></html>'
                    )
                return Response(RSS)

        transport = Transport()
        resolver = lambda *args: [(None, None, None, None, ("93.184.216.34", 443))]
        items = asyncio.run(
            FeedClient(client=transport, resolver=resolver).fetch(
                "https://example.org/journal"
            )
        )

        self.assertEqual("https://example.org/latest.xml", transport.urls[1])
        self.assertEqual("10.1000/example.1", items[0].doi)


class LiteratureDeduplicationTests(unittest.TestCase):
    def test_doi_pmid_openalex_and_normalized_url_each_prevent_duplicates(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.dedup import unique_items

        original = LiteratureItem(
            title="First",
            url="https://example.org/a?utm_source=x",
            doi="10.1000/ABC",
            pmid="123",
            openalex_id="W1",
        )
        values = [
            original,
            LiteratureItem(title="same DOI", url="https://other.org/1", doi="10.1000/abc"),
            LiteratureItem(title="same PMID", url="https://other.org/2", pmid="123"),
            LiteratureItem(title="same OpenAlex", url="https://other.org/3", openalex_id="W1"),
            LiteratureItem(title="same URL", url="https://example.org/a?ref=mail"),
            LiteratureItem(title="new", url="https://example.org/b", doi="10.1000/new"),
        ]

        self.assertEqual((original, values[-1]), unique_items(values))


class EuropePMCDiscoveryTests(unittest.TestCase):
    def test_literature_query_builds_one_reliable_query_and_normalizes_results(self):
        from extensions.subscriptions.discovery import EuropePMCClient
        from extensions.subscriptions.store import SubscriptionStore

        class Response:
            status_code = 200
            url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "resultList": {
                        "result": [
                            {
                                "title": "Causal &lt;i&gt;inference&lt;/i&gt; study",
                                "authorString": "A. Researcher",
                                "doi": "10.1000/causal",
                                "pmid": "987654",
                                "firstPublicationDate": "2026-07-31",
                                "abstractText": "Main conclusion.",
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

        class Transport:
            def __init__(self):
                self.params = None

            async def get(self, url, **kwargs):
                self.params = kwargs["params"]
                return Response()

        with TemporaryDirectory() as directory:
            subscription = SubscriptionStore(Path(directory)).create(
                kind="literature_query",
                name="因果推断",
                query='"target trial"',
                keywords=("cardiovascular",),
                daily_limit=3,
            )
        transport = Transport()
        items = asyncio.run(EuropePMCClient(client=transport).discover(subscription))

        self.assertIn('"target trial"', transport.params["query"])
        self.assertIn("cardiovascular", transport.params["query"])
        self.assertEqual(3, transport.params["pageSize"])
        self.assertEqual("P_PDATE_D desc", transport.params["sort"])
        self.assertEqual("10.1000/causal", items[0].doi)
        self.assertEqual("Causal inference study", items[0].title)
        self.assertTrue(items[0].open_access)
        self.assertEqual(
            "https://europepmc.org/articles/PMC1/bin/paper.pdf", items[0].pdf_url
        )

    def test_journal_issn_is_used_as_a_structured_query(self):
        from extensions.subscriptions.discovery import build_literature_query
        from extensions.subscriptions.store import SubscriptionStore

        with TemporaryDirectory() as directory:
            subscription = SubscriptionStore(Path(directory)).create(
                kind="journal",
                name="Example Medical Journal",
                source="1234-5678",
                query="cohort",
            )

        query = build_literature_query(subscription)
        self.assertIn('ISSN:"1234-5678"', query)
        self.assertNotIn('JOURNAL:"Example Medical Journal"', query)

    def test_journal_homepage_without_feed_falls_back_to_europe_pmc(self):
        from extensions.subscriptions.discovery import (
            DefaultLiteratureDiscoverer,
            LiteratureItem,
        )
        from extensions.subscriptions.store import SubscriptionStore

        class Feed:
            async def fetch(self, url):
                raise ValueError("no feed declaration")

        class PMC:
            async def discover(self, subscription):
                return (LiteratureItem(title="Fallback result", url="https://example.org/paper"),)

        class Enricher:
            async def enrich(self, item):
                return item

        with TemporaryDirectory() as directory:
            subscription = SubscriptionStore(Path(directory)).create(
                kind="journal",
                name="Example Medical Journal",
                source="https://example.org/journal",
            )
        result = asyncio.run(
            DefaultLiteratureDiscoverer(
                feed=Feed(), europe_pmc=PMC(), enricher=Enricher()
            ).discover(subscription)
        )

        self.assertEqual("Fallback result", result[0].title)


class LiteratureRunStoreTests(unittest.TestCase):
    def test_run_records_use_the_required_state_vocabulary(self):
        from extensions.subscriptions.runs import LiteratureRunStore

        with TemporaryDirectory() as directory:
            store = LiteratureRunStore(Path(directory))
            run = store.create("subscription-1")
            self.assertEqual("discovering", run.status)
            filtered = store.update(run.id, status="filtered", discovered=8, filtered=3)
            self.assertEqual(3, filtered.filtered)
            with self.assertRaises(ValueError):
                store.update(run.id, status="almost_done")


if __name__ == "__main__":
    unittest.main()
