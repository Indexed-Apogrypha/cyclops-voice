"""
Read tuning/results.jsonl, find candidates above a proxy threshold that
haven't been Gemini-judged yet, judge them, and write scores back.

Usage:
    python tuning/judge_top.py [--threshold 88] [--top N] [--results-file ...]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gemini-judge top proxy candidates")
    p.add_argument("--threshold", type=float, default=88.0,
                   help="Minimum proxy composite to qualify (default: 88)")
    p.add_argument("--top", type=int, default=8,
                   help="Maximum number of candidates to judge (default: 8)")
    p.add_argument("--results-file", default="tuning/results.jsonl")
    p.add_argument("--force", action="store_true",
                   help="Re-judge candidates that already have Gemini scores")
    args = p.parse_args(argv)

    results_file = ROOT / args.results_file
    if not results_file.exists():
        print(f"No results file at {results_file}")
        return 1

    rows = [json.loads(l) for l in results_file.read_text().splitlines() if l.strip()]

    # filter: above threshold, not already judged (unless --force)
    eligible = [
        r for r in rows
        if r.get("mean_proxy_composite", 0) >= args.threshold
        and (args.force or "gemini_total" not in r)
    ]
    eligible.sort(key=lambda r: r.get("mean_proxy_composite", 0), reverse=True)
    to_judge = eligible[: args.top]

    if not to_judge:
        print(f"No candidates above proxy threshold {args.threshold} needing Gemini judgement.")
        return 0

    print(f"Judging {len(to_judge)} candidate(s) via Gemini (proxy >= {args.threshold}):")
    for r in to_judge:
        print(f"  {r['candidate_id']:<30} proxy={r['mean_proxy_composite']}")

    from tuning.gemini_judge import judge_candidate

    for r in to_judge:
        cid = r["candidate_id"]
        candidate_dir = ROOT / "tuning" / "renders" / cid
        if not candidate_dir.exists():
            print(f"  SKIP {cid}: render dir not found")
            continue

        print(f"\n--- {cid} ---")
        try:
            result = judge_candidate(candidate_dir, candidate_id=cid)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # write scores back into the matching row
        for row in rows:
            if row["candidate_id"] == cid:
                row["gemini_total"] = result["total"]
                row["gemini_scores"] = result["scores"]
                row["gemini_defects"] = result.get("defects", [])
                row["gemini_strengths"] = result.get("strengths", [])
                row["gemini_model_notes"] = result.get("model_notes", "")
                break

        # persist after each judge call so progress is never lost
        results_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        print(f"  Gemini total: {result['total']}")
        for cat, score in result["scores"].items():
            print(f"    {cat:<30} {score}")
        if result.get("defects"):
            print(f"  Defects: {result['defects']}")

        time.sleep(1)  # be gentle on rate limits

    print("\nDone. Run: python tuning/results_view.py --metric gemini_total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
