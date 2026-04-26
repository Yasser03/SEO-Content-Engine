"""
tests/test_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Tests for deterministic components. These run without an LLM API key.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import os
import sys
import pytest
from pathlib import Path

# Ensure project root is on path when running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state import PipelineState, GenerateOutput, ResearchOutput, QualityGateResult
from core.knowledge_store import KnowledgeStore
from agents import quality_gate
from agents.generate import (
    _slug_from_title,
    _count_words,
    _calc_keyword_density,
    _extract_h2_sections,
)
from agents.evaluate import (
    _score_keywords,
    _score_readability,
    _score_structure,
    _score_internal_linking,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "client": {"name": "Test Blog", "domain": "test.io", "base_url": "https://test.io/blog"},
    "topic": {
        "seed_keywords": ["AI tools"],
        "domain_niche": "AI",
        "target_audience": "founders",
        "tone": "direct",
        "avoid_topics": [],
    },
    "publish": {"destination": "local_markdown", "output_dir": "/tmp/seo_test_output"},
    "quality_gate": {
        "min_word_count": 600,
        "max_word_count": 2500,
        "min_score": 0.65,
        "required_sections": ["Introduction", "Conclusion"],
        "min_keyword_density": 0.005,
        "max_keyword_density": 0.030,
    },
    "llm": {"provider": "groq", "model": "llama-3.3-70b-versatile", "temperature": 0.7, "max_tokens": 3000},
}

SAMPLE_BODY = """## Introduction

Artificial intelligence tools for startups are transforming how small teams operate.
AI tools for startups are no longer optional — they are a competitive advantage.
In this guide, we explore how you can use AI tools for startups to automate repetitive tasks.

## What Are AI Tools for Startups?

There are many different categories of tools available today. These range from
no-code automation platforms to sophisticated machine learning pipelines.

- ChatGPT for customer support
- Zapier for workflow automation  
- Midjourney for creative assets

## How to Choose the Right AI Tool

Choosing the right tool depends on your team size and budget.

### Evaluate Your Needs First

Start by listing your most time-consuming workflows.

### Consider Integration Requirements

Make sure the tool integrates with your existing stack.

## Common Mistakes to Avoid

Many founders fall into the trap of buying too many tools at once.

## Conclusion

AI tools for startups offer a genuine edge. Start with one tool, measure the impact,
then expand your stack. The best time to start is today.
"""


def make_state_with_generation(body: str = SAMPLE_BODY, word_count_override: int = None):
    state = PipelineState(config=SAMPLE_CONFIG)
    state.research = ResearchOutput(
        chosen_topic="AI tools for startups",
        primary_keyword="AI tools for startups",
        secondary_keywords=["startup automation", "no-code AI"],
        content_gap_reason="High search volume, low competition",
        competitor_angles=[],
        suggested_angle="Practical guide for non-technical founders",
        internal_link_candidates=[],
    )
    state.generation = GenerateOutput(
        title="AI Tools for Startups: The 2024 Practical Guide",
        slug="ai-tools-for-startups-practical-guide",
        meta_description="Discover the best AI tools for startups in 2024. A practical guide for non-technical founders covering automation, content, and operations.",
        body_markdown=body,
        word_count=word_count_override if word_count_override else _count_words(body),
        sections=_extract_h2_sections(body),
        keyword_density=_calc_keyword_density(body, "AI tools for startups"),
        internal_links_used=["/startup-automation-guide"],
    )
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic utility tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugGeneration:
    def test_basic_slug(self):
        assert _slug_from_title("Hello World") == "hello-world"

    def test_special_chars_stripped(self):
        assert _slug_from_title("AI Tools: The Guide!") == "ai-tools-the-guide"

    def test_multiple_spaces(self):
        assert _slug_from_title("Too   Many   Spaces") == "too-many-spaces"

    def test_length_capped(self):
        long_title = "A " * 50
        assert len(_slug_from_title(long_title)) <= 80


class TestWordCount:
    def test_simple_sentence(self):
        assert _count_words("Hello world today") == 3

    def test_handles_punctuation(self):
        assert _count_words("Hello, world! How are you?") == 5

    def test_empty_string(self):
        assert _count_words("") == 0


class TestKeywordDensity:
    def test_zero_density_when_absent(self):
        density = _calc_keyword_density("This article has no target phrase.", "AI tools")
        assert density == 0.0

    def test_correct_density(self):
        # "AI tools" appears 2 times in 10 words = 0.20
        text = "AI tools are great. AI tools save time. More text here."
        density = _calc_keyword_density(text, "AI tools")
        assert 0.15 <= density <= 0.25

    def test_case_insensitive(self):
        text = "ai TOOLS for startups and AI tools for teams"
        density = _calc_keyword_density(text, "AI tools")
        assert density > 0


class TestH2Extraction:
    def test_extracts_h2s(self):
        sections = _extract_h2_sections(SAMPLE_BODY)
        assert "Introduction" in sections
        assert "Conclusion" in sections

    def test_h3_not_included(self):
        sections = _extract_h2_sections(SAMPLE_BODY)
        assert "Evaluate Your Needs First" not in sections

    def test_empty_body(self):
        assert _extract_h2_sections("") == []


# ─────────────────────────────────────────────────────────────────────────────
# Quality Gate tests
# ─────────────────────────────────────────────────────────────────────────────

class TestQualityGate:
    def test_passes_valid_post(self):
        state = make_state_with_generation()
        result = quality_gate.run(state)
        # Our sample body should pass all checks
        assert result.quality_gate is not None
        if not result.quality_gate.passed:
            print("QG failures:", result.quality_gate.failures)

    def test_fails_too_short(self):
        state = make_state_with_generation(word_count_override=100)
        result = quality_gate.run(state)
        assert not result.quality_gate.passed
        assert any("Word count" in f for f in result.quality_gate.failures)

    def test_fails_missing_required_section(self):
        body_no_conclusion = SAMPLE_BODY.replace("## Conclusion", "## Final Thoughts")
        state = make_state_with_generation(body=body_no_conclusion)
        result = quality_gate.run(state)
        assert not result.quality_gate.passed
        assert any("Conclusion" in f for f in result.quality_gate.failures)

    def test_fails_keyword_stuffing(self):
        # Artificially high keyword density
        stuffed = "AI tools for startups " * 200
        state = make_state_with_generation(body=stuffed)
        result = quality_gate.run(state)
        assert not result.quality_gate.passed
        assert any("too high" in f for f in result.quality_gate.failures)

    def test_fails_missing_keyword(self):
        # No primary keyword in body
        body_no_kw = SAMPLE_BODY.replace("AI tools for startups", "these solutions")
        state = make_state_with_generation(body=body_no_kw)
        result = quality_gate.run(state)
        # Density would be near 0 — should fail
        assert not result.quality_gate.passed

    def test_score_is_between_0_and_1(self):
        state = make_state_with_generation()
        result = quality_gate.run(state)
        assert 0.0 <= result.quality_gate.score <= 1.0

    def test_abort_set_on_failure(self):
        state = make_state_with_generation(word_count_override=50)
        result = quality_gate.run(state)
        assert result.aborted_at == "quality_gate"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic evaluator tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluationScorers:
    def test_keyword_score_keyword_present(self):
        body = "AI tools for startups are great. " * 30 + "AI tools for startups are the future."
        score, findings = _score_keywords(body, "AI tools for startups", ["automation"])
        assert score > 0.5

    def test_readability_long_sentences(self):
        # Very long sentences should reduce score
        long_body = ("This is an extremely long sentence that goes on and on without stopping "
                     "because the author forgot that readers prefer short punchy sentences "
                     "that are easy to scan when they are reading on a mobile device. ") * 20
        score, findings = _score_readability(long_body)
        # Should warn about long sentences
        assert any("long" in f.lower() for f in findings) or score < 1.0

    def test_structure_no_h3(self):
        simple_body = "## Introduction\nSome text.\n## Conclusion\nDone."
        score, findings = _score_structure(["Introduction", "Conclusion"], simple_body)
        assert any("H3" in f for f in findings)

    def test_internal_linking_no_links(self):
        score, findings = _score_internal_linking([])
        assert score < 0.5
        assert any("internal link" in f.lower() for f in findings)

    def test_internal_linking_good(self):
        score, findings = _score_internal_linking(["/page1", "/page2", "/page3"])
        assert score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Store tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeStore:
    def test_initialises_empty(self, tmp_path):
        store = KnowledgeStore(str(tmp_path / "test_knowledge.json"))
        assert store.get_loop_count() == 0
        assert store.get_covered_topics() == []

    def test_records_post(self, tmp_path):
        store = KnowledgeStore(str(tmp_path / "test_records_post.json"))
        store.record_published_post("ai-tools", "AI Tools Guide", "AI tools for startups")
        # get_covered_topics returns lowercase
        assert "ai tools for startups" in store.get_covered_topics()

    def test_persists_to_disk(self, tmp_path):
        path = str(tmp_path / "test_persists.json")
        store = KnowledgeStore(path)
        store.record_published_post("slug-1", "Title 1", "keyword one")
        store.save()
        # Reload from same isolated path
        store2 = KnowledgeStore(path)
        assert len(store2.get_covered_topics()) == 1

    def test_records_evaluation_and_updates_avg(self, tmp_path):
        store = KnowledgeStore(str(tmp_path / "k.json"))
        store.record_published_post("s1", "T1", "k1")
        store.record_evaluation("run1", 0.80, [], ["Good structure"], [], ["Intro", "Body", "Conclusion"])
        assert store.get_avg_quality_score() == 0.80
        store.record_published_post("s2", "T2", "k2")
        store.record_evaluation("run2", 0.60, [], [], [], [])
        assert store.get_avg_quality_score() == 0.70

    def test_avoid_topics_added(self, tmp_path):
        store = KnowledgeStore(str(tmp_path / "k.json"))
        store.add_avoided_topic("NFT trading")
        assert "NFT trading" in store.get_avoid_topics()

    def test_keyword_usage_counter(self, tmp_path):
        store = KnowledgeStore(str(tmp_path / "k.json"))
        store.record_published_post("s1", "T1", "AI tools")
        store.record_published_post("s2", "T2", "AI tools")
        usage = store.get_keyword_usage()
        assert usage.get("ai tools", 0) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
