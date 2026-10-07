from lib.intelligence.ai.grounding import verified_context_block


def test_facts_and_evidence_are_included_with_ids():
    block, ids = verified_context_block(
        facts=[{"id": "fact-pe", "statement": "Trailing P/E is 18.2"}],
        evidence=[{"id": "ev-1", "headline": "Results filed", "source": "filing"}],
    )
    assert "Trailing P/E is 18.2" in block
    assert "fact-pe" in block
    assert "ev-1" in ids
    assert "Results filed" in block
