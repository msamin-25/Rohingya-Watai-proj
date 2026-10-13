"""Evaluate the matcher on an exported recordings folder.

    python -m rvb_ai.eval_matcher recordings/
    python -m rvb_ai.eval_matcher recordings/ --teach-speakers me --test-speakers friend

Teach takes become templates; test takes are scored against them. If there are no test takes,
every teach take is scored against the others (leave-one-out).

This command only REPORTS. It never changes the thresholds the app uses.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import recordings as rec
from .matcher import Matcher, PhraseScore, Template
from .safety import SENSITIVE, Decision, Thresholds, decide, margin_of

UNTAUGHT = "(never taught)"


@dataclass
class Trial:
    take_id: str
    speaker: str
    expected: str | None  # None => phrase was never taught (correct answer is "not sure")
    ranked: list[PhraseScore]
    decision: Decision

    @property
    def top1(self) -> str | None:
        return self.ranked[0].phrase_id if self.ranked else None

    @property
    def d1(self) -> float:
        return self.ranked[0].distance if self.ranked else math.inf

    @property
    def margin(self) -> float:
        return margin_of(self.ranked)

    @property
    def known(self) -> bool:
        return self.expected is not None

    @property
    def wrong_shown(self) -> bool:
        return self.decision.shown and self.decision.phrase_id != self.expected

    @property
    def correct_shown(self) -> bool:
        return self.decision.shown and self.decision.phrase_id == self.expected


def run_trials(data: rec.Recordings, t: Thresholds, teach_speakers=None, test_speakers=None):
    categories = {pid: p.get("category", "general") for pid, p in data.phrases.items()}
    teach = [x for x in data.takes if x.kind == "teach" and x.phrase_id and _ok(x.speaker, teach_speakers)]
    tests = [x for x in data.takes if x.kind == "test" and _ok(x.speaker, test_speakers)]
    matcher = Matcher()
    for x in teach:
        matcher.add(Template(x.phrase_id, x.features, x.id, x.speaker))
    taught = matcher.phrase_ids()

    mode = "test takes"
    if not tests:
        mode = "leave-one-out on teach takes (no test takes found)"
        tests, exclude = teach, True
    else:
        exclude = False

    trials = []
    for x in tests:
        ranked = matcher.rank(x.features, exclude_take=x.id if exclude else None)
        expected = x.phrase_id if x.phrase_id in taught else None
        if exclude and expected and not any(r.phrase_id == expected for r in ranked):
            continue  # only one take of this phrase; nothing to compare against
        trials.append(Trial(x.id, x.speaker, expected, ranked, decide(ranked, categories, t)))
    return trials, categories, taught, mode


def _ok(speaker: str, allowed) -> bool:
    return not allowed or speaker in allowed


def metrics(trials: list[Trial], categories: dict[str, str]) -> dict:
    known = [x for x in trials if x.known]
    untaught = [x for x in trials if not x.known]
    n = len(trials)
    shown = [x for x in trials if x.decision.shown]
    return {
        "trials": n,
        "known_trials": len(known),
        "untaught_trials": len(untaught),
        "top1_accuracy": _rate(sum(x.top1 == x.expected for x in known), len(known)),
        "shown_rate": _rate(len(shown), n),
        "correct_shown_rate": _rate(sum(x.correct_shown for x in known), len(known)),
        "wrong_and_shown_rate": _rate(sum(x.wrong_shown for x in trials), n),
        "wrong_and_shown": sum(x.wrong_shown for x in trials),
        "untaught_shown": sum(x.decision.shown for x in untaught),
        "sensitive_wrong_shown": sum(
            x.wrong_shown and categories.get(x.decision.phrase_id or "", "") in SENSITIVE for x in trials
        ),
        "status_counts": dict(Counter(x.decision.status for x in trials)),
    }


def confusions(trials: list[Trial]) -> list[tuple[str, str, int]]:
    c = Counter((x.expected or UNTAUGHT, x.top1 or "-") for x in trials if x.known and x.top1 != x.expected)
    return [(a, b, k) for (a, b), k in c.most_common()]


def _rate(a: int, b: int) -> float | None:
    return a / b if b else None


def _simulate(trials: list[Trial], categories: dict[str, str], t: Thresholds) -> tuple[int, int, int]:
    """(wrong_shown, correct_shown, sensitive_wrong_shown) if these thresholds were used."""
    wrong = correct = sens = 0
    for x in trials:
        d = decide(x.ranked, categories, t)
        if d.shown and d.phrase_id == x.expected:
            correct += 1
        elif d.shown:
            wrong += 1
            sens += categories.get(d.phrase_id or "", "") in SENSITIVE
    return wrong, correct, sens


def suggest(trials: list[Trial], categories: dict[str, str], current: Thresholds) -> dict:
    """Search for thresholds that show zero wrong answers while showing as many right ones as possible.

    Returns evidence + a suggestion. Nothing is applied.
    """
    good = sorted(x.d1 for x in trials if x.known and x.top1 == x.expected and math.isfinite(x.d1))
    bad = sorted(x.d1 for x in trials if (not x.known or x.top1 != x.expected) and math.isfinite(x.d1))
    evidence = {
        "correct_top1_distance": _summary(good),
        "wrong_or_untaught_distance": _summary(bad),
    }
    if len([x for x in trials if x.known]) < 10:
        return {"evidence": evidence, "suggestion": None, "why": "Fewer than 10 known test takes: not enough data."}

    # Candidate accept distances sit in the gaps between observed distances, so a choice never
    # lands exactly on a recording.
    d1s = sorted({x.d1 for x in trials if math.isfinite(x.d1)})
    candidates = {round((a + b) / 2, 3) for a, b in zip(d1s, d1s[1:])} | {current.accept_distance}
    results = []
    for acc in sorted(candidates):
        for marg in (0.0, 0.04, 0.08, 0.12, 0.16, 0.2, 0.25, 0.3):
            t = Thresholds(acc, marg, min(current.strong_distance, acc), max(current.strong_margin, marg))
            wrong, correct, _ = _simulate(trials, categories, t)
            results.append((wrong, -correct, marg, acc))
    # 1) fewest wrong answers shown, 2) most right answers shown, 3) the strictest margin,
    # 4) the middle of the remaining distance range (largest buffer on both sides).
    best = min(r[:2] for r in results)
    tied = [r for r in results if r[:2] == best]
    marg = max(r[2] for r in tied)
    accs = sorted(r[3] for r in tied if r[2] == marg)
    acc = accs[len(accs) // 2]

    # Strong (sensitive) distance: at least a 10% buffer below the closest wrong/never-taught take.
    strong_d = min(acc, bad[0] * 0.9) if bad else acc
    proposal = Thresholds(acc, marg, round(strong_d, 3), round(max(current.strong_margin, marg), 3))
    p_wrong, p_correct, p_sens = _simulate(trials, categories, proposal)
    c_wrong, c_correct, c_sens = _simulate(trials, categories, current)
    looser = [
        k
        for k in ("strong_distance",)
        if getattr(proposal, k) > getattr(current, k)
    ] + [k for k in ("strong_margin",) if getattr(proposal, k) < getattr(current, k)]
    return {
        "evidence": evidence,
        "current": {"thresholds": current.to_dict(), "wrong_shown": c_wrong, "correct_shown": c_correct, "sensitive_wrong_shown": c_sens},
        "suggestion": {"thresholds": proposal.to_dict(), "wrong_shown": p_wrong, "correct_shown": p_correct, "sensitive_wrong_shown": p_sens},
        "loosens_sensitive_gate": looser,
        "why": "Fewest wrong answers shown, then most right answers shown, then the strictest margin and the "
        "middle of the safe distance range.",
    }


def _summary(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"n": len(values), "min": round(values[0], 3), "median": round(statistics.median(values), 3), "max": round(values[-1], 3)}


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:.1f}%"


def report(trials, categories, taught, mode, current: Thresholds, english: dict[str, str]) -> str:
    m = metrics(trials, categories)
    s = suggest(trials, categories, current)
    name = lambda pid: english.get(pid, pid) if pid not in (None, UNTAUGHT, "-") else (pid or "-")  # noqa: E731
    out = []
    out.append(f"Mode: {mode}")
    out.append(f"Taught phrases: {len(taught)} | trials: {m['trials']} (known {m['known_trials']}, never-taught {m['untaught_trials']})")
    out.append("")
    out.append("RESULTS with the current thresholds")
    out.append(f"  Top-1 accuracy (closest phrase is right):  {_pct(m['top1_accuracy'])}")
    out.append(f"  Shown and correct (of known takes):        {_pct(m['correct_shown_rate'])}")
    out.append(f"  WRONG and shown (of all takes):            {_pct(m['wrong_and_shown_rate'])}  ({m['wrong_and_shown']} takes)")
    out.append(f"  Never-taught phrases that were shown:      {m['untaught_shown']}")
    out.append(f"  Sensitive phrases shown wrongly:           {m['sensitive_wrong_shown']}  (must be 0)")
    out.append(f"  Outcomes: {m['status_counts']}")
    out.append("")
    conf = confusions(trials)
    out.append("CONFUSIONS (said -> closest match)" if conf else "CONFUSIONS: none")
    for a, b, k in conf:
        out.append(f"  {name(a)!s:40} -> {name(b)!s:40} x{k}")
    out.append("")
    out.append("PER TAKE (distance: lower = more similar; margin: gap to the next phrase)")
    for x in sorted(trials, key=lambda x: (x.expected or "~", x.d1)):
        flag = "WRONG-SHOWN" if x.wrong_shown else ("ok" if x.correct_shown else "")
        out.append(
            f"  {name(x.expected or UNTAUGHT)[:32]:32} top1={name(x.top1)[:28]:28} d={x.d1:6.3f} margin={x.margin:5.2f} "
            f"{x.decision.status:18} {flag}"
        )
    out.append("")
    out.append("EVIDENCE")
    out.append(f"  Distances when the closest phrase was right:    {s['evidence']['correct_top1_distance']}")
    out.append(f"  Distances when wrong or never taught:           {s['evidence']['wrong_or_untaught_distance']}")
    out.append("")
    if s["suggestion"] is None:
        out.append(f"SUGGESTION: none. {s['why']}")
    else:
        out.append("SUGGESTION (NOT applied - the app still uses the current values)")
        out.append(f"  current:   {s['current']['thresholds']}  -> wrong shown {s['current']['wrong_shown']}, correct shown {s['current']['correct_shown']}")
        out.append(f"  suggested: {s['suggestion']['thresholds']}  -> wrong shown {s['suggestion']['wrong_shown']}, correct shown {s['suggestion']['correct_shown']}")
        out.append(f"  rule: {s['why']}")
        if s["loosens_sensitive_gate"]:
            out.append(f"  WARNING: this would loosen the sensitive-phrase gate ({', '.join(s['loosens_sensitive_gate'])}). Needs more data and a human decision.")
        if m["known_trials"] < 30:
            out.append(f"  CAUTION: only {m['known_trials']} known test takes; treat this as a first estimate.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m rvb_ai.eval_matcher", description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=Path, help="unzipped export folder (contains manifest.json)")
    ap.add_argument("--teach-speakers", nargs="*", help="only use teach takes from these speakers")
    ap.add_argument("--test-speakers", nargs="*", help="only score test takes from these speakers")
    ap.add_argument("--thresholds", type=Path, help="JSON file with thresholds to evaluate instead of the defaults")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args(argv)

    current = Thresholds(**json.loads(args.thresholds.read_text())) if args.thresholds else Thresholds()
    try:
        data = rec.load(args.folder)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    trials, categories, taught, mode = run_trials(data, current, args.teach_speakers, args.test_speakers)
    if not trials:
        print("error: nothing to evaluate. Teach at least 2 takes per phrase, or record test takes.", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"mode": mode, "metrics": metrics(trials, categories), "confusions": confusions(trials), **suggest(trials, categories, current)}, indent=2))
    else:
        english = {pid: p.get("english", pid) for pid, p in data.phrases.items()}
        print(report(trials, categories, taught, mode, current, english))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
