from __future__ import annotations

from services.interpretation_bridge import EntityStore, InterpretationBridge


def _bridge():
    return InterpretationBridge(EntityStore(session_factory=None, tenant_id="tenant-type-signal"))


def test_interpretation_bridge_extracts_type_signal_for_an_existing_mention():
    html = b"""<!doctype html>
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Person","name":"Ada Lovelace"}
      </script>
    </head><body>
      <h1>Ada Lovelace</h1>
      <p>Ada Lovelace works for Analytical Engines Ltd.</p>
    </body></html>"""
    result = _bridge().interpret(
        html, capture_ref="CAP-type-signal", content_type="text/html",
        investigation_id="CASE-type-signal", source_id="fixture:public-biography",
    )
    assert result.mentions > 0
    assert len(result.type_signals) == 1
    signal = result.type_signals[0]
    assert signal.surface == "Person"
    assert signal.source_vocab == "schema.org"
    assert signal.mention_ref in {item.mention_id for item in result.document.mentions}
    assert signal.observation_refs == (result.observation_id,)
    assert result.type_signal_refusals == ()


def test_interpretation_bridge_refuses_invalid_structured_type_without_minting_mention():
    # This is deliberately malformed JSON-LD and all visible prose is lowercase. No
    # name/mention is supplied to the generic extractor, so the structured adapter must
    # preserve a typed parse refusal rather than manufacturing a person from @type/name.
    html = b"""<html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"person","name": }
      </script>
    </head><body><p>ordinary source material contains only lowercase words</p></body></html>"""
    result = _bridge().interpret(
        html, capture_ref="CAP-invalid-type", content_type="text/html",
        investigation_id="CASE-type-signal", source_id="fixture:public-biography",
    )
    assert result.mentions == 0
    assert result.type_signals == ()
    assert any(item["code"] == "jsonld_invalid" for item in result.type_signal_refusals)
