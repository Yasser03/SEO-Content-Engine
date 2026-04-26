"""
pipeline.py
─────────────────────────────────────────────────────────────────────────────
Orchestrates the five-stage SEO content loop.
State flows explicitly through each stage — no globals, no shared mutation.
─────────────────────────────────────────────────────────────────────────────
"""

import yaml
import sys
from pathlib import Path

from core.state import PipelineState
from core.knowledge_store import KnowledgeStore
from core.llm_client import LLMClient
from agents import research, generate, quality_gate, publish, evaluate, learn


def load_config(config_path: str = "config/client.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_loop(
    config_path: str = "config/client.yaml",
    store_path: str = "store/knowledge.json",
    dry_run: bool = False,
) -> PipelineState:
    """
    Execute one complete loop iteration.
    Returns the final PipelineState (useful for testing).
    """
    print("=" * 65)
    print("  SEO-Content-Engine — Autonomous Loop")
    print("=" * 65)

    # ── Initialise shared dependencies ───────────────────────────────────────
    config = load_config(config_path)
    store = KnowledgeStore(store_path)
    llm = LLMClient(config)

    print(f"\n  Client: {config['client']['name']}")
    print(f"  Loop #{store.get_loop_count() + 1}")
    print(f"  Store state: {store.summary()}")

    # ── Initialise state ─────────────────────────────────────────────────────
    state = PipelineState(config=config)

    # ── Stage 1: Research ────────────────────────────────────────────────────
    state = research.run(state, store, llm)
    if state.aborted_at:
        _abort(state)
        return state

    # ── Stage 2: Generate ────────────────────────────────────────────────────
    state = generate.run(state, store, llm)
    if state.aborted_at:
        _abort(state)
        return state

    # ── Stage 2b: Quality Gate ───────────────────────────────────────────────
    state = quality_gate.run(state)
    if state.aborted_at:
        _abort(state)
        # Still run Learn so failures are recorded and inform future loops
        state = learn.run(state, store)
        return state

    if dry_run:
        print("\n[DRY RUN] Stopping before publish.")
        return state

    # ── Stage 3: Publish ─────────────────────────────────────────────────────
    state = publish.run(state)
    if state.aborted_at:
        _abort(state)
        return state

    # ── Stage 4: Evaluate ────────────────────────────────────────────────────
    state = evaluate.run(state, llm)
    if state.aborted_at:
        _abort(state)
        return state

    # ── Stage 5: Learn ───────────────────────────────────────────────────────
    state = learn.run(state, store)

    print("\n" + "=" * 65)
    print("  Loop complete ✓")
    print(f"  Post: '{state.generation.title}'")
    print(f"  Quality gate score: {state.quality_gate.score:.2f}")
    print(f"  Evaluation score:   {state.evaluation.overall_score:.2f}")
    print(f"  Published to:       {state.publish.destination_path}")
    print("=" * 65 + "\n")

    return state


def _abort(state: PipelineState):
    print(f"\n  ✗ Pipeline aborted at stage: {state.aborted_at}")
    for err in state.errors:
        print(f"    Error: {err}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run one SEO content loop")
    parser.add_argument("--config", default="config/client.yaml", help="Path to client config")
    parser.add_argument("--store", default="store/knowledge.json", help="Path to knowledge store")
    parser.add_argument("--dry-run", action="store_true", help="Stop before publishing")
    args = parser.parse_args()

    state = run_loop(
        config_path=args.config,
        store_path=args.store,
        dry_run=args.dry_run,
    )

    sys.exit(0 if not state.aborted_at else 1)
