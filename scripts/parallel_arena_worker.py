#!/usr/bin/env python3
"""Default local worker adapter for Parallel Arena lanes.

This worker is intentionally local and deterministic: it performs no provider calls, no network access,
and no shell execution. It gives the dashboard a real subprocess-backed lane execution path while keeping
provider-backed/delegate workers free to replace this script later under the same JSON input/output contract.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path


def _score(strategy: str, task: str, index: int) -> int:
    lowered = f"{strategy} {task}".lower()
    score = 45 + max(0, 18 - index * 3)
    for keyword, bonus in {
        "test": 10,
        "verify": 10,
        "research": 8,
        "implement": 8,
        "critic": 7,
        "review": 7,
        "benchmark": 10,
        "dashboard": 6,
        "parallel": 5,
        "artifact": 4,
    }.items():
        if keyword in lowered:
            score += bonus
    return min(score, 99)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: parallel_arena_worker.py INPUT_JSON OUTPUT_JSON", file=sys.stderr)
        return 2
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    task = str(payload.get("task") or "")
    strategy = str(payload.get("strategy") or "strategy")
    index = int(payload.get("index") or 0)
    lane_dir = Path(payload.get("lane_dir") or output_path.parent)
    lane_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = lane_dir / "worker_artifact.json"
    plan_path = lane_dir / "lane_proposal.md"
    scorecard_path = lane_dir / "scorecard.json"
    start = time.monotonic()
    focus_terms = [term for term in re.split(r"[^A-Za-z0-9_-]+", strategy.lower()) if term]
    artifact = {
        "task_digest": task[:400],
        "strategy": strategy,
        "worker": "parallel_arena_worker.py",
        "focus_terms": focus_terms,
        "execution_contract": ["input.json", "result.json", "worker_artifact.json", "stdout.txt", "stderr.txt"],
        "notes": [
            "Executed as a local subprocess worker lane.",
            "No external provider spend, network access, or nested shell commands are used by this default worker.",
        ],
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plan_lines = [
        f"# Parallel Arena Lane Proposal: {strategy}",
        "",
        "## Task",
        task[:1200] or "(empty task)",
        "",
        "## Approach",
        f"- Optimize for: {', '.join(focus_terms[:8]) or 'general execution'}",
        "- Keep changes bounded, test-backed, and artifact-producing.",
        "- Hand off this proposal to a model-backed/delegate lane when provider spend is enabled.",
        "",
        "## Verification",
        "- Preserve input.json/result.json/stdout.txt/stderr.txt for audit.",
        "- Review scorecard.json before promoting a winner.",
    ]
    plan_path.write_text("\n".join(plan_lines) + "\n", encoding="utf-8")
    scorecard = {
        "score": _score(strategy, task, index),
        "rubric": {
            "bounded": True,
            "testable": any(term in {"test", "verify", "benchmark"} for term in focus_terms),
            "artifact_backed": True,
            "provider_spend": False,
        },
        "focus_terms": focus_terms,
    }
    scorecard_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "status": "completed",
        "score": scorecard["score"],
        "summary": f"Local worker completed lane '{strategy}' and persisted browsable proposal/scorecard artifacts.",
        "artifacts": artifact,
        "artifact_paths": {"worker_artifact": str(artifact_path), "lane_proposal": str(plan_path), "scorecard": str(scorecard_path)},
        "duration_ms": int((time.monotonic() - start) * 1000),
        "safety_notes": ["local subprocess", "no provider spend", "no network", "no shell delegation"],
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "artifact": str(artifact_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
