"""
Quick results viewer — reads tuning/results.jsonl and prints a ranked summary.

Usage:
    python tuning/results_view.py [--results-file tuning/results.jsonl] [--top N]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="View and rank tuning results")
    p.add_argument("--results-file", default="tuning/results.jsonl")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--metric", default="mean_proxy_composite",
                   choices=["mean_proxy_composite", "gemini_total"])
    args = p.parse_args(argv)

    path = ROOT / args.results_file
    if not path.exists():
        print(f"No results file at {path}. Run render_matrix.py first.")
        return 1

    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if not rows:
        print("No results yet.")
        return 0

    rows.sort(key=lambda r: r.get(args.metric, 0), reverse=True)

    # header
    print(f"\n{'RANK':<5} {'CANDIDATE':<40} {'PROXY':>7} {'GEMINI':>7}  PARAMS")
    print("-" * 100)

    for i, r in enumerate(rows[: args.top], 1):
        proxy = r.get("mean_proxy_composite", "—")
        gemini = r.get("gemini_total", "—")
        cid = r.get("candidate_id", "?")[:40]
        ps = r.get("pitch_semitones", "?")
        ls = r.get("length_scale", "?")
        preset = r.get("preset", {})
        lm_gain = preset.get("lowmid_gain_db", "?")
        lp = preset.get("lowpass_hz", "?")
        print(
            f"#{i:<4} {cid:<40} {proxy:>7} {gemini:>7}"
            f"  pitch={ps} len={ls} lm_gain={lm_gain}dB lp={lp}Hz"
        )

    print()

    # show metric breakdown for top result
    top = rows[0]
    print(f"=== Metric breakdown: {top.get('candidate_id')} ===")
    combined = top.get("combined_proxy", {})
    for k, v in combined.get("metrics", {}).items():
        flag = "OK" if v.get("pass") else "XX"
        print(f"  {flag} {k:<20} {str(v.get('value')):<10} target: {v.get('target')}")

    if "gemini_scores" in top:
        print(f"\n=== Gemini rubric scores: {top.get('candidate_id')} ===")
        for cat, score in top["gemini_scores"].items():
            print(f"  {cat:<30} {score}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
