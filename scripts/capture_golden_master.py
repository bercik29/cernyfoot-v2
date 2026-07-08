"""Capture a golden master of the ORIGINAL app's statistics output.

Runs the original `statistics.py` (path-patched, never modified on disk) against a
temporary, drift-corrected copy of the match data, and freezes the result as JSON.
Phase 5's SQL stats engine must reproduce these numbers exactly (acceptance
criterion 6).

Drift correction applies rule D2: within each match file, every row's score is
rewritten to the score of the first data row that has one.

Usage:
    .venv/bin/python -m scripts.capture_golden_master \
        --source ../cernyfoot [--out scripts/output/golden_master.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

DATE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")


def build_corrected_copy(stats_dir: Path, dest: Path) -> list[str]:
    """Copy match files into `dest`, applying D2 drift correction. Returns the
    list of files that were corrected."""
    corrected = []
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(stats_dir.iterdir()):
        if not DATE_NAME_RE.match(f.name):
            continue  # drop 19:00.csv and anything else stray
        with open(f, "r", newline="", encoding="utf-8-sig") as fh:
            rows = [row for row in csv.reader(fh) if row]
        header, data = (rows[0], rows[1:]) if rows and rows[0][0] == "Player" else (
            ["Player", "Team", "Score"], rows)
        scores = [r[2] for r in data if len(r) > 2 and r[2]]
        if scores and len(set(scores)) > 1:
            canonical = scores[0]
            for r in data:
                if len(r) > 2:
                    r[2] = canonical
            corrected.append(f.name)
        with open(dest / f.name, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(data)
    return corrected


def load_original_module(original_root: Path, stats_dir: Path, cancelled_file: Path):
    """Exec the original statistics.py with its hard-coded paths redirected."""
    src = (original_root / "statistics.py").read_text(encoding="utf-8")
    src = src.replace(
        "'/home/bercik29/cernyfoot/static/statistics'", repr(str(stats_dir))
    ).replace(
        "'/home/bercik29/cernyfoot/static/cancelled_matches.csv'", repr(str(cancelled_file))
    )
    assert "/home/bercik29" not in src, "path patching failed — original file changed?"
    namespace: dict = {"__name__": "original_statistics"}
    exec(compile(src, "original_statistics.py", "exec"), namespace)
    return namespace


def jsonable(obj):
    """Recursively convert sets/tuples/dict-tuple-keys into JSON-safe structures."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(x) for x in obj]
    if isinstance(obj, set):
        return sorted(jsonable(x) for x in obj)
    return obj


def registered_nicknames(original_root: Path) -> list[str]:
    with open(original_root / "static" / "users.csv", newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if r and len(r) > 2]
    return [r[2].strip() for r in rows[1:] if r[2].strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="path to the original app root (contains statistics.py and static/)")
    parser.add_argument("--out", default="scripts/output/golden_master.json")
    args = parser.parse_args()

    original_root = Path(args.source).resolve()
    stats_src = original_root / "static" / "statistics"
    cancelled = original_root / "static" / "cancelled_matches.csv"

    with tempfile.TemporaryDirectory() as tmp:
        corrected_dir = Path(tmp) / "statistics"
        corrected = build_corrected_copy(stats_src, corrected_dir)
        mod = load_original_module(original_root, corrected_dir, cancelled)

        seasons = list(mod["SEASONS"].keys())
        players = registered_nicknames(original_root)

        master = {
            "note": "Output of the ORIGINAL statistics.py over drift-corrected (D2) data.",
            "drift_corrected_files": corrected,
            "seasons": {},
        }
        for season in seasons:
            master["seasons"][season] = {
                "global": jsonable(mod["calculate_global_statistics"](season=season)),
                "players": {
                    p: jsonable(mod["calculate_player_statistics"](p, season=season))
                    for p in players
                },
            }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(master, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"golden master written to {out}")
    print(f"drift-corrected files: {corrected}")
    for season in master["seasons"]:
        g = master["seasons"][season]["global"]
        print(f"  {season}: matches_played={g['total_matches_played'][0]}, "
              f"goals={g['total_goals_scored']}, league_rows={len(g['all_players_stats'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
