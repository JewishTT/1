"""Unit tests for Layer 2 entity resolution (spec/010 §0.8) — pure math, no AI."""

from __future__ import annotations

import pytest

from zero.harvesters.contracts import ObservationCandidate
from zero.resolution.fellegi_sunter import (
    FellegiSunter,
    block_pairs,
    email_field,
    name_field,
    phone_field,
)
from zero.resolution.graph import (
    cluster_candidates,
    community_detection,
    connected_components,
    greedy_modularity,
    modularity,
)
from zero.resolution.similarity import (
    idf_weight,
    jaro,
    jaro_winkler,
    levenshtein,
    normalize,
    token_dice,
)

# ---------------------------------------------------------------------------
# similarity primitives
# ---------------------------------------------------------------------------


class TestStringSimilarity:
    def test_levenshtein_known_cases(self) -> None:
        assert levenshtein("kitten", "sitting") == 3
        assert levenshtein("", "") == 0
        assert levenshtein("abc", "") == 3
        assert levenshtein("same", "same") == 0

    def test_jaro_bounds(self) -> None:
        assert jaro("martha", "marhta") > jaro("martha", "zxcvbs")
        assert 0.0 <= jaro("abc", "xyz") <= 1.0

    def test_jaro_winkler_prefix_bonus(self) -> None:
        base = jaro("martha", "marhta")
        boosted = jaro_winkler("martha", "marhta")
        assert boosted >= base
        assert jaro_winkler("Robert", "Roberta") > 0.8  # JW threshold sensitivity

    def test_normalize_canonical_forms(self) -> None:
        assert normalize(" John.Smith@Example.COM ", "email") == "john.smith@example.com"
        assert normalize("+1 (202) 555-0199", "phone") == "12025550199"
        assert normalize("EXAMPLE.com/", "domain") == "example.com"
        assert normalize("  John  Smythe ", "name") == "john smythe"


# ---------------------------------------------------------------------------
# blocking
# ---------------------------------------------------------------------------


class TestBlockingAndSoundex:
    DUPLICATES = [
        {"name": "John Smith", "email": "john.smith@acme.com", "phone": "+12025550199"},
        {"name": "Jon Smythe", "email": "jsmith@acme.com", "phone": "+1 202 555 0199"},
        {"name": "Jonn Smithers", "email": "jsmithers@acme.com", "phone": "+12025550199"},
        {"name": "Alice Lee", "email": "alice@corp.co", "phone": "+14155550123"},
        {"name": "Alice", "email": "alice@corp.co", "phone": "+14155550124"},
    ]

    def test_block_pairs_find_phone_and_email_blocks(self) -> None:
        pairs = block_pairs(self.DUPLICATES)
        assert (0, 1) in pairs  # same phone digits + soundex-close name
        assert (3, 4) in pairs  # same email local alias
        assert len(pairs) > 0

    def test_block_keys_exclude_unrelated(self) -> None:
        pairs = block_pairs(self.DUPLICATES, key_fields=("email",))
        # no email overlap with alice pair unless exact alias matches
        assert (0, 1) not in pairs  # different emails, phone-only link irrelevant


# ---------------------------------------------------------------------------
# Fellegi-Sunter
# ---------------------------------------------------------------------------


def _synth_corpus() -> list[dict]:
    entities = [
        [
            ("John Smith", "john.smith@acme.com", "+12025550199"),
            ("Jon Smythe", "jsmith@acme.com", "+1 202 555 0199"),
            ("J Smith", "j.smith@acme.co", "+12025550199"),
        ],
        [
            ("Alice Lee", "alice@corp.co", "+14155550123"),
            ("Alicia Leigh", "alicia.leigh@corp.co", "+14155550123"),
            ("Alice Leigh", "al@corp.co", "+14155550123"),
        ],
        [
            ("Bob King", "bob.king@corp.co", "+16503331111"),
            ("Bobby King", "bobking@corp.co", "+1 650 333 1111"),
            ("Robert King", "r.king@corp.co", "+16503331111"),
        ],
        [
            ("Chloe Dubois", "chloe@globe.io", "+33140888888"),
            ("Chloé Dubois", "c.dubois@globe.io", "+33 1 40 88 88 88"),
            ("Cloe Dub", "clo@globe.io", "+33140888888"),
        ],
    ]
    return [
        {"name": name, "email": email, "phone": phone}
        for group in entities
        for name, email, phone in group
    ]


def _training_pairs(records: list[dict]) -> list[tuple[int, int]]:
    """Blocked pairs plus unrelated (control) pairs so EM sees contrast.

    EM needs both matching and non-matching pairs: the raw candidate set
    (``block_pairs``) is match-rich, so a few clearly unrelated pairs are
    added — standard record-linkage practice.
    """
    pairs = set(block_pairs(records))
    for entity in range(4):
        seed = ((entity + 1) % 4) * 3
        for offset in range(3):
            a = entity * 3 + offset
            b = seed
            if a != b and a // 3 != b // 3:
                pairs.add((a, b) if a < b else (b, a))
    return sorted(pairs)


class TestFellegiSunter:
    FIELDS = (name_field(), email_field(), phone_field())

    def test_fit_is_deterministic_and_repeatable(self) -> None:
        records = _synth_corpus()
        pairs = _training_pairs(records)
        model_a = FellegiSunter(self.FIELDS, lambda_prior=0.1).fit(records, pairs)
        model_b = FellegiSunter(self.FIELDS, lambda_prior=0.1).fit(records, pairs)
        assert model_a._m == model_b._m
        assert model_a._u == model_b._u

    def test_duplicates_outweigh_unrelated(self) -> None:
        records = _synth_corpus()
        model = FellegiSunter(self.FIELDS, lambda_prior=0.1).fit(records, _training_pairs(records))
        dup_weight = model.weight(records[0], records[1])  # same person, phone+close name
        unrelated_weight = model.weight(records[0], records[3])  # different person
        assert dup_weight > unrelated_weight
        assert dup_weight > 0.0
        assert unrelated_weight < 0.0

    def test_match_recovers_duplicate_pairs(self) -> None:
        records = _synth_corpus()
        model = FellegiSunter(self.FIELDS, lambda_prior=0.1).fit(records, _training_pairs(records))
        matches = model.match(records, threshold=0.0)
        pairs = {(a, b) for a, b, _weight in matches}
        for entity in range(4):
            a, b, c = entity * 3, entity * 3 + 1, entity * 3 + 2
            assert (a, b) in pairs and (a, c) in pairs and (b, c) in pairs
        assert not any(a // 3 != b // 3 for a, b in pairs)  # no cross-entity links

    def test_weight_tf_boosts_rare_values(self) -> None:
        records = _synth_corpus()
        model = FellegiSunter(self.FIELDS, lambda_prior=0.1).fit(records, block_pairs(records))
        matched = model.weight(records[4], records[5])
        tf_weighted = model.weight_tf(records[4], records[5])
        assert tf_weighted >= matched  # exact email is rare-ish boost

    def test_tf_idf_function(self) -> None:
        assert idf_weight("bob", corpus_count=100, token_frequency=50) < idf_weight(
            "bob", corpus_count=100, token_frequency=1
        )


class TestComparisonLevelPredicates:
    def test_exact_email_level(self) -> None:
        field = email_field()
        vector = [level.test("a@x.co", "a@x.co") for level in field.levels]
        assert vector == [True, True]
        vector2 = [level.test("a@x.co", "b@y.co") for level in field.levels]
        assert vector2 == [False, True]  # falls through to catch-all

    def test_name_levels_chain(self) -> None:
        field = name_field()
        exact_index = 0
        soundex_index = 1
        jaro_index = 2
        catchall_index = 3
        assert field.levels[soundex_index].test("John Smith", "Jon Smythe")
        assert not field.levels[exact_index].test("John Smith", "Jon Smythe")
        assert field.levels[jaro_index].test("John Smith", "Jon Smythe")
        assert field.levels[catchall_index].test("aaaaaa", "bbbbbb")


# ---------------------------------------------------------------------------
# graph topology
# ---------------------------------------------------------------------------


class TestGraphTopology:
    def test_transitive_closure(self) -> None:
        # A~B, B~C, and separate D~E must become two clusters
        clusters = connected_components(5, [(0, 1), (1, 2), (3, 4)])
        assert {0, 1, 2} in clusters
        assert {3, 4} in clusters

    def test_transitive_closure_single(self) -> None:
        clusters = connected_components(3, [(0, 1)])
        assert len(clusters) == 2
        assert {2} in clusters

    def test_greedy_modularity_is_deterministic(self) -> None:
        adjacency = {
            (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
            (3, 4): 1.0, (3, 5): 1.0, (4, 5): 1.0,
            (2, 3): 0.1,
        }
        first = greedy_modularity(6, adjacency, passes=3)
        second = greedy_modularity(6, adjacency, passes=3)
        assert first == second

    def test_modularity_reference_values(self) -> None:
        # two disjoint weight-1 triangles, hand-computed Newman-Girvan values
        adjacency = {
            (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
            (3, 4): 1.0, (3, 5): 1.0, (4, 5): 1.0,
        }
        split = [0, 0, 0, 1, 1, 1]
        singletons = [0, 1, 2, 3, 4, 5]
        assert modularity(6, adjacency, split) == pytest.approx(0.0)
        assert modularity(6, adjacency, singletons) == pytest.approx(-1 / 6)

    def test_modularity_label_relabeling_invariant(self) -> None:
        adjacency = {(0, 1): 1.0, (1, 2): 1.0, (2, 0): 1.0, (3, 4): 1.0, (4, 5): 1.0}
        labeled = modularity(6, adjacency, [0, 0, 0, 1, 1, 1])
        relabeled = modularity(6, adjacency, [1, 1, 1, 0, 0, 0])
        assert labeled == relabeled

    def test_structural_partition_exceeds_modularity(self) -> None:
        # two disjoint triangles: a "correct" split is strictly better than all-singletons
        adjacency = {
            (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
            (3, 4): 1.0, (3, 5): 1.0, (4, 5): 1.0,
        }
        split = [0, 0, 0, 1, 1, 1]
        singletons = [0, 1, 2, 3, 4, 5]
        assert modularity(6, adjacency, split) > modularity(6, adjacency, singletons)

    def test_community_detection_covers_all_nodes(self) -> None:
        adjacency = {
            (0, 1): 1.0, (0, 2): 1.0, (1, 2): 1.0,
            (3, 4): 1.0, (3, 5): 1.0, (4, 5): 1.0,
            (2, 3): 0.1,
        }
        communities = community_detection(6, adjacency)
        assert sorted(node for group in communities for node in group) == [0, 1, 2, 3, 4, 5]


class TestClusterCandidates:
    def test_merges_same_contact_keeps_max_confidence(self) -> None:
        candidates = [
            ObservationCandidate("alice@corp.co", "email", 0.8, "a", "m-a"),
            ObservationCandidate("ALICE@corp.co", "email", 0.9, "b", "m-b"),
            ObservationCandidate("+12025550199", "phone", 0.7, "c", "m-c"),
        ]
        merged = cluster_candidates(candidates)
        emails = [c for c in merged if c.kind == "email"]
        assert len(emails) == 1
        assert emails[0].confidence == pytest.approx(0.9)
        sources = emails[0].raw_fields.get("sources", "")
        assert "a," in sources or "b," in sources

    def test_min_confidence_filters(self) -> None:
        candidates = [
            ObservationCandidate("a@x.co", "email", 0.2, "m1", "mm"),
            ObservationCandidate("b@y.co", "email", 0.7, "m2", "mm"),
        ]
        merged = cluster_candidates(candidates, min_confidence=0.5)
        assert [c.value for c in merged] == ["b@y.co"]


class TestTokenMetrics:
    def test_token_dice(self) -> None:
        assert token_dice("Acme Group Ltd", "Acme Group") > token_dice("Acme Group Ltd", "Boeing")