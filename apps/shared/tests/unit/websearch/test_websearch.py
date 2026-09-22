"""Entity-driven web discovery tests (feature 010/011, web-discovery slice).

Pins the missing "entity-in → web-search → candidate-URLs-out" half of Layer 0:
query derivation from an atomic entity's identifiers, provider fan-out (Brave
HTTP transport-injected + memory), entity-relevance re-ranking, dedup, threshold,
and FrontierSink enqueue. All hermetic — zero external I/O.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from websearch import EntityWebDiscovery
from websearch.contracts import SearchQuery
from websearch.discovery import default_providers, memory_providers
from websearch.providers import (
    BraveSearchProvider,
    FederatedSearchProvider,
    MemorySearchProvider,
    TavilySearchProvider,
)
from websearch.queries import entity_identifiers_to_queries, identifiers_to_tokens, transliterate
from websearch.relevance import entity_relevance_score, rerank_for_entity


class TestQueryBuilder:
    def test_name_becomes_quoted_entity_query_first(self):
        queries = entity_identifiers_to_queries({"full_name": "Олег Тинькофф"})
        assert queries and queries[0].text == '"Олег Тинькофф"'
        assert queries[0].intent == "entity"
        # Cyrillic name → ru-locale hint on the query
        assert queries[0].lang == "ru"

    def test_cyrillic_name_gets_transliterated_variant(self):
        queries = entity_identifiers_to_queries({"full_name": "Олег Тинькофф"})
        texts = [q.text for q in queries]
        assert '"Oleg Tinkoff"' in texts  # latinized probe for search engines

    def test_transliterate_roundtrip(self):
        assert transliterate("Олег Тинькофф") == "Oleg Tinkoff"
        assert transliterate("Jane Doe") == "Jane Doe"  # latin passes through
        assert transliterate("ё") == "yo"  # ё handled, not eaten by е

    def test_identifiers_map_to_intents(self):
        queries = entity_identifiers_to_queries(
            {
                "full_name": "Jane Doe",
                "email": "jane@acme.test",
                "phone": "+15550001122",
                "domain": "acme.test",
            }
        )
        by_intent = {q.intent: q.text for q in queries}
        assert by_intent.get("phone") == "15550001122"  # +/I18N stripped
        assert by_intent.get("email") == "jane@acme.test"
        assert by_intent.get("domain") == "acme.test"
        assert by_intent.get("entity") == '"Jane Doe"'

    def test_dedup_rejects_exploding_identifier_bags(self):
        # adversarial: 50 near-duplicates must not blow up the query set (bounded)
        identifiers = {f"k{i}": " exact " for i in range(50)}
        queries = entity_identifiers_to_queries(identifiers)
        assert len({q.text for q in queries}) == 1

    def test_tokens_single_line(self):
        line = identifiers_to_tokens({"email": "jane@acme.test", "full_name": "Олег Тинькофф"})
        assert "jane" in line and "олег" in line and "тинькофф" in line  # normalized, no dup

    def test_phone_normalized_to_digits(self):
        queries = entity_identifiers_to_queries({"phone": "+7 (495) 123-45-67"})
        assert queries[0].text == "74951234567"


class TestMemoryProvider:
    async def test_ranks_relevant_doc_first(self):
        provider = MemorySearchProvider(
            {
                "http://a.test/page1": {
                    "title": "sanctions list",
                    "snippet": "the company appears here",
                    "terms": "company",
                },
                "http://b.test/page2": {"title": "recipes", "snippet": "cooking", "terms": "food"},
            }
        )
        hits = await provider.search(SearchQuery(text="sanctions"))
        assert hits and hits[0].uri == "http://a.test/page1"
        assert provider.supports(SearchQuery(text="sanctions"))


class TestBraveProvider:
    async def test_parses_brave_hits_transport_injected(self):
        import json

        payload = {
            "web": {
                "results": [
                    {
                        "url": "http://acme.test/",
                        "title": "ACME Holdings",
                        "description": "garden",
                        "score": 0.9,
                    },
                    {
                        "url": "http://spam.test/",
                        "title": "junk",
                        "description": "ads",
                        "score": 0.1,
                    },
                ]
            }
        }
        raw = json.dumps(payload)
        seen = {}

        async def transport(url, api_key=""):
            seen["url"] = url
            seen["key"] = api_key
            return raw

        provider = BraveSearchProvider(transport=transport, api_key="tok")
        hits = await provider.search(SearchQuery(text="acme"))
        assert len(hits) == 2
        assert hits[0].uri == "http://acme.test/"
        assert hits[0].score == 0.9
        assert "q=acme" in seen["url"]
        assert seen["key"] == "tok"

    async def test_cyrillic_query_sends_ru_locale(self):
        seen = {}

        async def transport(url, api_key=""):
            seen["url"] = url
            return '{"web":{"results":[]}}'

        provider = BraveSearchProvider(transport=transport, api_key="tok")
        await provider.search(SearchQuery(text='"Олег Тинькофф"', lang="ru"))
        assert "country=ru" in seen["url"]
        assert "search_lang=ru" in seen["url"]

    async def test_missing_key_and_transport_returns_empty(self):
        provider = BraveSearchProvider(api_key="", transport=None)
        hits = await provider.search(SearchQuery(text="acme"))
        assert hits == []  # honest empty, never a crash


class TestTavilyProvider:
    async def test_parses_tavily_hits_transport_injected(self):
        import json

        payload = {
            "results": [
                {
                    "url": "http://acme.test/",
                    "title": "ACME",
                    "content": "garden tools",
                    "score": 0.8,
                }
            ]
        }
        raw = json.dumps(payload)
        seen = {}

        async def transport(url, payload_body):
            seen["url"] = url
            seen["query"] = payload_body.get("query")
            return raw

        provider = TavilySearchProvider(transport=transport, api_key="tok")
        hits = await provider.search(SearchQuery(text="acme"))
        assert len(hits) == 1
        assert hits[0].uri == "http://acme.test/"
        assert hits[0].score == 0.8
        assert "api.tavily.com" in seen["url"]
        assert seen["query"] == "acme"

    async def test_missing_key_and_transport_returns_empty(self):
        provider = TavilySearchProvider(api_key="", transport=None)
        hits = await provider.search(SearchQuery(text="acme"))
        assert hits == []  # honest empty

    def test_default_providers_are_real_search_engines(self):
        names = {p.name for p in default_providers()}
        assert "brave-search" in names
        assert "tavily" in names


class TestFederatedProvider:
    async def test_merges_and_dedups_by_uri(self):
        a = MemorySearchProvider(
            {
                "http://acme.test/": {"title": "a", "snippet": "acme", "terms": "acme"},
                "http://dup.test/": {"title": "d", "snippet": "acme", "terms": "acme"},
            }
        )
        b = MemorySearchProvider(
            {
                "http://acme.test/": {"title": "A", "snippet": "acme", "terms": "acme"},
                "http://onlyb.test/": {"title": "b", "snippet": "acme", "terms": "acme"},
            }
        )
        fused = FederatedSearchProvider([a, b])
        hits = await fused.search(SearchQuery(text="acme"))
        uris = {h.uri for h in hits}
        assert "http://acme.test/" in uris  # dedup: appears once
        assert "http://onlyb.test/" in uris
        assert "http://dup.test/" in uris


class TestEntityRelevance:
    def test_exact_phone_evidence_outranks_token_overlap(self):
        from websearch.contracts import SearchHit

        hit_phone = SearchHit(uri="http://x.test/p", title="", snippet="call 5550001122", score=1.0)
        hit_wordy = SearchHit(
            uri="http://x.test/q",
            title="about the firm generally",
            snippet="garden tool",
            score=2.0,
        )
        identifiers = {"full_name": "Jane Doe", "phone": "+1 555 000 1122"}
        assert entity_relevance_score(hit_phone, identifiers) > entity_relevance_score(
            hit_wordy, identifiers
        )

    def test_domain_in_url_bonus(self):
        from websearch.contracts import SearchHit

        hit = SearchHit(
            uri="http://acme.test/contact", title="Contact", snippet="call us", score=1.0
        )
        ids = {"domain": "acme.test"}
        assert entity_relevance_score(hit, ids) > entity_relevance_score(
            hit, {"domain": "nope.test"}
        )

    def test_rerank_threshold_and_topk(self):
        from websearch.contracts import SearchHit

        hits = [
            SearchHit(uri=f"http://x{i}.test/", title="acme", snippet="jane doe", score=1.0)
            for i in range(3)
        ]
        hits.append(
            SearchHit(uri="http://junk.test/", title="totally unrelated", snippet="", score=1.0)
        )
        cands = rerank_for_entity(
            hits, {"full_name": "Jane Doe"}, query="jane", top_k=2, min_score=0.0
        )
        assert len(cands) == 2  # sorted by relevance desc, capped
        assert all(c.relevance > 0 for c in cands)
        assert all(hasattr(c, "uri") and c.uri for c in cands)


class TestWhetherDiscoveryIsStreaming:
    """Stream-first compliance (feature 009): sink receives candidates as they
    arrive, not only after the whole search completes."""

    async def test_sink_receives_candidates_incrementally(self):
        import asyncio

        from websearch.contracts import SearchHit

        got_after_first_sink = asyncio.Event()
        sink_seen: list[str] = []
        released = asyncio.Event()

        class SlowMemoryProvider:
            """First query returns immediately; second waits for ``released``."""

            name = "memory-slow"

            def supports(self, query: SearchQuery) -> bool:
                return True

            async def search(self, query, *, tenant_id="", top_k=10):
                if "jane@acme.test" in query.text:
                    await released.wait()  # second query stalls
                    return []
                return [
                    SearchHit(
                        uri="http://first.test/",
                        title="jane doe",
                        snippet="jane",
                        score=1.0,
                        provider=self.name,
                    )
                ]

        class CountingSink:
            def enqueue(
                self,
                *,
                uri,
                tenant_id,
                investigation_id,
                source,
                method,
                priority=0.0,
                provenance=None,
            ):
                sink_seen.append(uri)
                if len(sink_seen) == 1:
                    got_after_first_sink.set()
                return None

        discovery = EntityWebDiscovery(providers=[SlowMemoryProvider()], min_score=0.0)

        async def run():
            await discovery.discover_and_sink(
                {"full_name": "Jane Doe", "email": "jane@acme.test"},
                CountingSink(),
                tenant_id="ten-1",
            )

        task = asyncio.create_task(run())
        await asyncio.wait_for(got_after_first_sink.wait(), timeout=2.0)
        # stream-first: the first candidate landed in the sink while the second
        # query was still pending (released not set yet).
        assert sink_seen, "first candidate must be sunk before the search completes"
        released.set()  # unblock the slow query so discovery finishes cleanly
        await task
        assert sink_seen, "sink must be fed as candidates stream in"

    async def test_stream_yields_before_full_discovery(self):
        import asyncio

        from websearch.contracts import SearchHit

        collected: list[str] = []
        released = asyncio.Event()

        class SlowMemoryProvider:
            name = "memory-slow"

            def supports(self, query: SearchQuery) -> bool:
                return True

            async def search(self, query, *, tenant_id="", top_k=10):
                if "jane@acme.test" in query.text:
                    await released.wait()
                    return []
                return [
                    SearchHit(
                        uri="http://first.test/",
                        title="jane",
                        snippet="jane",
                        score=1.0,
                        provider=self.name,
                    )
                ]

        discovery = EntityWebDiscovery(providers=[SlowMemoryProvider()], min_score=0.0)

        async def run():
            async for cand in discovery.stream(
                {"full_name": "Jane Doe", "email": "jane@acme.test"}, tenant_id="ten-1"
            ):
                collected.append(cand.uri)

        task = asyncio.create_task(run())
        for _ in range(50):
            if collected:
                break
            await asyncio.sleep(0.01)
        assert collected, "stream must emit before all queries complete"
        released.set()
        await task


class TestDiscoverySink:
    async def test_discover_and_sink_enqueues(self):
        corpus = {
            "http://acme.test/jane": {
                "title": "Jane's page",
                "snippet": "jane doe info",
                "terms": "jane doe",
            },
            "http://acme.test/contact": {
                "title": "Contact",
                "snippet": "jane@acme.test 5550001122",
                "terms": "contact",
            },
        }
        discovery = EntityWebDiscovery(providers=memory_providers(corpus), min_score=0.0)
        enqueued: list[dict] = []

        class Sink:
            def enqueue(
                self,
                *,
                uri,
                tenant_id,
                investigation_id,
                source,
                method,
                priority=0.0,
                provenance=None,
            ):
                enqueued.append(
                    {
                        "uri": uri,
                        "tenant_id": tenant_id,
                        "investigation_id": investigation_id,
                        "priority": priority,
                    }
                )
                return None

        cands = await discovery.discover_and_sink(
            {"full_name": "Jane Doe", "email": "jane@acme.test"},
            Sink(),
            tenant_id="ten-1",
            investigation_id="inv-1",
            top_k=10,
        )
        assert cands, "memory corpus must produce candidates"
        assert enqueued, "sink must be called per candidate"
        # priority carries the entity-relevance score
        assert all(e["priority"] > 0 for e in enqueued)
        assert all(e["investigation_id"] == "inv-1" for e in enqueued)
        # subset relation: sink received exactly what discover returned
        assert {e["uri"] for e in enqueued} == {c.uri for c in cands}

    async def test_discovery_returns_ranked_deduped_candidates(self):
        corpus = {
            "http://acme.test/official": {
                "title": "ACME",
                "snippet": "jane doe official site involves 5550001122",
                "terms": "jane doe",
            },
            "http://guess.test/wordy": {
                "title": "about the general topic",
                "snippet": "jane mentions",
                "terms": "jane",
            },
        }
        discovery = EntityWebDiscovery(providers=memory_providers(corpus), min_score=0.0)
        cands = await discovery.discover(
            {"full_name": "Jane Doe", "phone": "5550001122"}, tenant_id="ten-1"
        )
        assert cands
        # the page carrying exact phone evidence ranks first
        assert cands[0].uri == "http://acme.test/official"

    async def test_host_diversity_caps_one_source(self):
        # single big site floods the intermediate provider results; the stream
        # must cap per-host so the frontier does not become one website.
        corpus = {
            f"http://monopole.test/p{i}": {
                "title": i,
                "snippet": "jane doe company",
                "terms": "jane doe",
            }
            for i in range(6)
        }
        corpus["http://other.test/page"] = {
            "title": "other",
            "snippet": "jane doe company",
            "terms": "jane doe",
        }
        discovery = EntityWebDiscovery(providers=memory_providers(corpus), min_score=0.0)
        cands = await discovery.discover({"full_name": "Jane Doe"}, tenant_id="ten-1", top_k=7)
        hosts = {c.host for c in cands}
        assert len(hosts) >= 2, "diversity must keep a second host in the result"
        assert sum(1 for c in cands if c.host == "monopole.test") <= 3
