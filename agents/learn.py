"""
agents/learn.py  —  Stage 5: Learn
─────────────────────────────────────────────────────────────────────────────
Feeds evaluation results back into the persistent knowledge store.
After this stage, the NEXT loop's Research and Generate stages will:
  • Know what topic was just covered (won't repeat it)
  • Have access to high-performing structural patterns to emulate
  • Know which angles performed well (preferred_angles)
  • Know what to improve (stored as low_performing_patterns)

This is the feedback mechanism that makes the loop self-improving.
─────────────────────────────────────────────────────────────────────────────
"""

import json
from pathlib import Path
from datetime import datetime, UTC

from core.state import PipelineState
from core.knowledge_store import KnowledgeStore


def run(state: PipelineState, store: KnowledgeStore) -> PipelineState:
    print("\n[Stage 5 / Learn] Updating knowledge store …")

    if not state.evaluation or not state.generation:
        state.errors.append("Learn: missing evaluation or generation output — nothing to learn")
        return state

    g = state.generation
    r = state.research
    e = state.evaluation

    # 1. Record the published post (prevents topic repetition in future loops)
    store.record_published_post(
        slug=g.slug,
        title=g.title,
        primary_keyword=r.primary_keyword,
    )

    # 2. Record evaluation results (updates rolling averages, patterns)
    store.record_evaluation(
        run_id=state.run_id,
        score=e.overall_score,
        findings=e.findings,
        strengths=e.strengths,
        improvements=e.improvements,
        sections=g.sections,
    )

    # 3. If score was poor, flag the topic angle to avoid
    if e.overall_score < 0.50:
        store.add_avoided_topic(r.suggested_angle)
        print(f"  → Low score ({e.overall_score:.2f}): angle added to avoid list")

    # 4. Persist to disk
    store.save()

    # 5. Write a human-readable evaluation report alongside the post
    report_dir = Path("output/evaluations")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{state.run_id}_evaluation.json"

    report = {
        "run_id": state.run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "post_title": g.title,
        "post_slug": g.slug,
        "primary_keyword": r.primary_keyword,
        "quality_gate": {
            "passed": state.quality_gate.passed,
            "score": state.quality_gate.score,
            "failures": state.quality_gate.failures,
            "warnings": state.quality_gate.warnings,
        },
        "evaluation": {
            "overall_score": e.overall_score,
            "semantic_coverage_score": e.semantic_coverage_score,
            "keyword_score": e.keyword_score,
            "readability_score": e.readability_score,
            "structural_score": e.structural_score,
            "internal_linking_score": e.internal_linking_score,
            "findings": e.findings,
            "strengths": e.strengths,
            "improvements": e.improvements,
        },
        "knowledge_store_summary": store.summary(),
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  → Evaluation report: {report_path}")
    print(f"  → Store state: {store.summary()}")

    return state
