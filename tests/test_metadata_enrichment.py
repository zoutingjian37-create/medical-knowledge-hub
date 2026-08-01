import asyncio
import unittest


class MetadataEnrichmentTests(unittest.TestCase):
    def test_crossref_and_openalex_complete_identifiers_authors_and_open_pdf(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.enrichment import MetadataEnricher

        class Response:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class Transport:
            async def get(self, url, **kwargs):
                if "crossref.org" in url:
                    return Response(
                        {
                            "message": {
                                "title": ["Completed title"],
                                "author": [{"given": "Ada", "family": "Researcher"}],
                                "abstract": "<jats:p>Main conclusion.</jats:p>",
                                "published": {"date-parts": [[2026, 7, 31]]},
                                "URL": "https://doi.org/10.1000/complete",
                            }
                        }
                    )
                return Response(
                    {
                        "id": "https://openalex.org/W123",
                        "doi": "https://doi.org/10.1000/complete",
                        "open_access": {"is_oa": True},
                        "best_oa_location": {
                            "pdf_url": "https://repository.example/paper.pdf"
                        },
                    }
                )

        item = LiteratureItem(
            title="",
            url="https://doi.org/10.1000/complete",
            doi="10.1000/complete",
        )
        enriched = asyncio.run(MetadataEnricher(client=Transport()).enrich(item))

        self.assertEqual("Completed title", enriched.title)
        self.assertEqual("Ada Researcher", enriched.authors)
        self.assertEqual("Main conclusion.", enriched.abstract)
        self.assertEqual("W123", enriched.openalex_id)
        self.assertEqual("https://repository.example/paper.pdf", enriched.pdf_url)
        self.assertTrue(enriched.open_access)

    def test_metadata_api_failure_keeps_the_discovered_record(self):
        import httpx
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.enrichment import MetadataEnricher

        class Transport:
            async def get(self, url, **kwargs):
                raise httpx.ConnectError("offline")

        item = LiteratureItem(
            title="Already discovered",
            url="https://doi.org/10.1000/offline",
            doi="10.1000/offline",
        )

        self.assertEqual(item, asyncio.run(MetadataEnricher(client=Transport()).enrich(item)))


if __name__ == "__main__":
    unittest.main()
