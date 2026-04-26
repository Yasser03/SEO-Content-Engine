"""
agents/publish.py  —  Stage 3: Publish
─────────────────────────────────────────────────────────────────────────────
Writes the approved post to its destination.
Currently supports:
  • local_markdown   — writes a .md file with YAML frontmatter
  • webhook          — POST JSON payload to a CMS endpoint

The destination is configured per client. Switching to a Contentful or
Ghost API would only require updating config.yaml + adding a new handler here.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import requests
from datetime import datetime, UTC
from pathlib import Path

from core.state import PipelineState, PublishOutput


def _build_markdown_file(state: PipelineState) -> str:
    """Assemble full markdown file with YAML frontmatter."""
    g = state.generation
    r = state.research
    now = datetime.now(UTC).strftime("%Y-%m-%d")

    frontmatter = f"""---
title: "{g.title}"
slug: "{g.slug}"
date: "{now}"
meta_description: "{g.meta_description}"
primary_keyword: "{r.primary_keyword}"
secondary_keywords: {r.secondary_keywords}
word_count: {g.word_count}
keyword_density: {g.keyword_density}
quality_score: {state.quality_gate.score}
run_id: "{state.run_id}"
---

# {g.title}

"""
    return frontmatter + g.body_markdown


def run(state: PipelineState) -> PipelineState:
    print("\n[Stage 3 / Publish] Writing post to destination …")

    if not state.generation or not state.quality_gate or not state.quality_gate.passed:
        state.errors.append("Publish: called but quality gate did not pass — skipping")
        state.aborted_at = "publish"
        return state

    cfg = state.config
    pub_cfg = cfg["publish"]
    destination = pub_cfg.get("destination", "local_markdown")

    if destination == "local_markdown":
        output_dir = Path(pub_cfg.get("output_dir", "output/posts"))
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{state.run_id}_{state.generation.slug[:40]}.md"
        filepath = output_dir / filename
        content = _build_markdown_file(state)
        with open(filepath, "w") as f:
            f.write(content)
        destination_path = str(filepath)
        print(f"  → Published to: {destination_path}")

    elif destination == "webhook":
        webhook_url = pub_cfg.get("webhook_url", "")
        if not webhook_url:
            state.errors.append("Publish: webhook destination configured but webhook_url is empty")
            state.aborted_at = "publish"
            return state

        payload = {
            "title": state.generation.title,
            "slug": state.generation.slug,
            "meta_description": state.generation.meta_description,
            "body_markdown": state.generation.body_markdown,
            "primary_keyword": state.research.primary_keyword,
            "run_id": state.run_id,
        }
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            destination_path = f"{webhook_url} (HTTP {resp.status_code})"
            print(f"  → Published via webhook: {destination_path}")
        except requests.RequestException as e:
            state.errors.append(f"Publish: webhook failed: {e}")
            state.aborted_at = "publish"
            return state

    else:
        state.errors.append(f"Publish: unknown destination '{destination}'")
        state.aborted_at = "publish"
        return state

    state.publish = PublishOutput(
        published=True,
        destination_path=destination_path,
        timestamp=datetime.now(UTC).isoformat(),
    )
    return state
