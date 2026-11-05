"""Fixed recommendation rules over the report model (Phase 12f, ADR-0032).

No model is called. Each rule is a pure function returning its recommendations and any
"not enough data" notes, and states the numbers and the threshold that fired so the
reader can disagree with it. Every threshold and minimum sample is in ``THRESHOLDS``.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from time import localtime

from phx.progress import fmt_dur, fmt_tokens
from phx.report.model import PhaseUse, Report, Totals, median


@dataclass(frozen=True)
class Threshold:
    value: float
    reason: str


THRESHOLDS: dict[str, Threshold] = {
    "r1_min_phases": Threshold(5, "a median of fewer phases says little about one model"),
    "r1_cost_multiple": Threshold(3, "below 3x the median a phase is ordinary variation"),
    "r1_min_excess_usd": Threshold(2, "a multiple of a tiny cost is not worth a look"),
    "r2_min_sessions": Threshold(10, "a few bad sessions are not a pattern"),
    "r2_share": Threshold(0.20, "one fifth lost is worth finding out why"),
    "r3_min_phases": Threshold(5, "the comparison needs a median of similar phases"),
    "r3_low_cost_fraction": Threshold(0.5, "half the model's median cost marks an easy phase"),
    "r3_short_s": Threshold(1800, "30 minutes marks an easy phase"),
    "r3_trouble_sessions": Threshold(2, "one failed session can be chance; two are a signal"),
    "r4_min_sessions": Threshold(5, "cache share is noisy over a few sessions"),
    "r4_cache_share": Threshold(0.5, "long sessions normally read well over half from cache"),
    "r4_min_tokens": Threshold(1_000_000, "a small model's few tokens cannot waste much"),
    "r5_min_waits": Threshold(3, "fewer waits are incidents, not a pattern"),
    "r5_wait_share": Threshold(0.25, "a quarter of working time is a real delay"),
    "r5_pattern_waits": Threshold(5, "a time-of-day pattern needs several waits"),
    "r5_pattern_share": Threshold(0.6, "most waits in one slot is a pattern, not chance"),
    "r5_min_gate_pauses": Threshold(3, "a median needs a few pauses"),
    "r5_gate_median_s": Threshold(14400, "4 hours held at a gate is most of a working session"),
    "r6_min_idle_kills": Threshold(3, "one or two kills may be real hangs"),
    "r6_near_wall": Threshold(0.9, "within 10% of the cap counts as hitting it"),
    "r6_min_sessions": Threshold(20, "the longest session needs a fair sample"),
    "r6_loose_wall": Threshold(0.25, "a cap 4x the longest session guards little"),
    "r7_min_sessions": Threshold(3, "a period with fewer sessions is too noisy to trend"),
    "r7_rise": Threshold(0.10, "a rise under 10% is noise"),
    "r8_min_sessions": Threshold(10, "providers compare only on a fair sample each"),
    "r8_gap": Threshold(0.25, "a smaller gap in completion rate may be the phases, not them"),
}


def limit(name: str) -> float:
    return THRESHOLDS[name].value


@dataclass(frozen=True)
class Recommendation:
    id: str
    severity: str  # "advice" or "info"
    title: str
    evidence: tuple[str, ...]
    action: str
    threshold: str


Result = tuple[list[Recommendation], list[str]]


def not_enough(rule: str, what: str, have: int, needs: float) -> str:
    return f"not enough data for {rule} ({count(have, what)}, needs {needs:.0f})"


def count(n: int, noun: str) -> str:
    """``1 phase``, ``3 phases``; ``noun`` may carry a suffix (``phases on x``)."""
    head, _, tail = noun.partition(" ")
    word = head if n != 1 else head.removesuffix("s")
    return " ".join(part for part in (str(n), word, tail) if part)


def money(value: float | None) -> str:
    return "unknown" if value is None else f"${value:,.2f}"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _name(row: PhaseUse) -> str:
    return f"{row.project} {row.phase}"


def r1_cost_concentration(report: Report) -> Result:
    recs: list[Recommendation] = []
    notes: list[str] = []
    groups: dict[str, list[PhaseUse]] = {}
    for row in report.phases:
        if row.totals.cost_usd is not None:
            groups.setdefault(row.model, []).append(row)
    multiple = limit("r1_cost_multiple")
    excess = limit("r1_min_excess_usd")
    for model, rows in sorted(groups.items()):
        if len(rows) < limit("r1_min_phases"):
            notes.append(not_enough(f"R1 on {model}", "phases", len(rows), limit("r1_min_phases")))
            continue
        mid = median(r.totals.cost_usd or 0.0 for r in rows) or 0.0
        high = [
            r
            for r in rows
            if (r.totals.cost_usd or 0.0) >= mid * multiple
            and (r.totals.cost_usd or 0.0) - mid >= excess
        ]
        if not high:
            continue
        recs.append(
            Recommendation(
                "R1",
                "advice",
                f"{len(high)} of {len(rows)} phases on {model} cost far above its median",
                tuple(
                    f"{_name(r)}: {money(r.totals.cost_usd)} over {r.totals.sessions} session(s), "
                    f"median {money(mid)}"
                    for r in high[:5]
                ),
                "Look at what made these phases expensive; a large phase may split into two.",
                f"cost >= {multiple:g}x the model's median and at least ${excess:g} above it",
            )
        )
    return recs, notes


def r2_noncompleting(report: Report) -> Result:
    t = report.totals
    needs = limit("r2_min_sessions")
    if t.sessions < needs:
        return [], [not_enough("R2", "sessions", t.sessions, needs)]
    share = limit("r2_share")
    cost = t.noncompleting_cost_share
    span = t.noncompleting_time_share
    if (cost or 0.0) < share and (span or 0.0) < share:
        return [], []
    worst = sorted(
        (r for r in report.phases if r.totals.noncompleting_sessions),
        key=lambda r: (-r.totals.noncompleting_active_s, r.project, r.phase),
    )
    classes = Counter(s.cls for s in report.sessions if not s.completing)
    return [
        Recommendation(
            "R2",
            "advice",
            "A large share of spend went to sessions that did not complete their phase",
            (
                f"{t.noncompleting_sessions} of {t.sessions} sessions did not complete: "
                + ", ".join(f"{n} {name}" for name, n in sorted(classes.items())),
                f"{percent(cost)} of known cost ({money(t.noncompleting_cost_usd)}) and "
                f"{percent(span)} of active time ({fmt_dur(t.noncompleting_active_s)}); "
                "cost is a lower bound, a killed session's cost lands on the next run",
                *(
                    f"{_name(r)}: {r.totals.noncompleting_sessions} session(s), "
                    f"{fmt_dur(r.totals.noncompleting_active_s)}"
                    for r in worst[:3]
                ),
            ),
            "Read `phx log` for those phases: split work that outruns a session or usage "
            "window, and fix what keeps stalling them.",
            f"non-completing share of cost or time >= {share * 100:.0f}%",
        )
    ], []


def _verified(row: PhaseUse) -> bool:
    return row.totals.cost_usd is not None and not row.totals.unverified_cost_usd


def r3_model_fit(report: Report) -> Result:
    needs = limit("r3_min_phases")
    recs: list[Recommendation] = []
    notes: list[str] = []
    strong = [
        r for r in report.phases if r.alias == "opus" and r.totals.phases_completed and _verified(r)
    ]
    if len(strong) < needs:
        notes.append(not_enough("R3 (strongest model)", "phases", len(strong), needs))
    else:
        mid = median(r.totals.cost_usd or 0.0 for r in strong) or 0.0
        low = limit("r3_low_cost_fraction") * mid
        short = limit("r3_short_s")
        easy = [
            r
            for r in strong
            if r.totals.first_attempt
            and (r.totals.cost_usd or 0.0) <= low
            and r.totals.active_s <= short
        ]
        if easy:
            recs.append(
                Recommendation(
                    "R3",
                    "info",
                    f"{count(len(easy), 'phases on the strongest model')} quick and cheap",
                    tuple(
                        f"{_name(r)}: {money(r.totals.cost_usd)}, "
                        f"{fmt_dur(r.totals.active_s)}, first attempt"
                        for r in sorted(easy, key=lambda r: r.totals.cost_usd or 0.0)[:5]
                    ),
                    "A balanced model may suffice for similar phases; weigh this against the "
                    "reason the plan gives for its model choice.",
                    f"first attempt, cost <= {limit('r3_low_cost_fraction') * 100:.0f}% of the "
                    f"median {money(mid)}, at most {fmt_dur(short)}",
                )
            )
    balanced = [r for r in report.phases if r.alias == "sonnet"]
    if len(balanced) < needs:
        notes.append(not_enough("R3 (balanced model)", "phases", len(balanced), needs))
    else:
        trouble = limit("r3_trouble_sessions")
        hard = [
            r
            for r in balanced
            if r.totals.noncompleting_sessions >= trouble or r.totals.blocks >= trouble
        ]
        if hard:
            recs.append(
                Recommendation(
                    "R3",
                    "info",
                    f"{count(len(hard), 'phases on a balanced model')} needed repeated attempts",
                    tuple(
                        f"{_name(r)}: {r.totals.noncompleting_sessions} non-completing "
                        f"session(s), {r.totals.blocks} block(s), {money(r.totals.cost_usd)}"
                        for r in hard[:5]
                    ),
                    "The strongest model may save money on similar phases; weigh this against "
                    "the reason the plan gives for its model choice.",
                    f"at least {trouble:g} non-completing sessions or blocks",
                )
            )
    return recs, notes


def r4_cache(report: Report) -> Result:
    needs = limit("r4_min_sessions")
    share = limit("r4_cache_share")
    recs: list[Recommendation] = []
    notes: list[str] = []
    for model, t in sorted(report.by_model.items()):
        if t.sessions < needs:
            notes.append(not_enough(f"R4 on {model}", "sessions", t.sessions, needs))
            continue
        read = t.cache_read_share
        if read is None or read >= share or t.tokens.total < limit("r4_min_tokens"):
            continue
        recs.append(
            Recommendation(
                "R4",
                "advice",
                f"Low cache-read share on {model}",
                (
                    f"{percent(read)} of input came from cache over {t.sessions} sessions: "
                    f"{fmt_tokens(t.tokens.cache_read)} read, "
                    f"{fmt_tokens(t.tokens.cache_write)} written, "
                    f"{fmt_tokens(t.tokens.input)} uncached",
                ),
                "Sessions may be re-reading or re-creating large contexts: shorten what each "
                "phase must load first.",
                f"cache-read share < {share * 100:.0f}%",
            )
        )
    return recs, notes


_BLOCKS = ("00:00-06:00", "06:00-12:00", "12:00-18:00", "18:00-24:00")
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _wait_pattern(starts: list[float]) -> str | None:
    """The time slot most waits start in, if one clearly dominates."""
    if len(starts) < limit("r5_pattern_waits"):
        return None
    slots = Counter(_BLOCKS[localtime(s).tm_hour // 6] for s in starts)
    days = Counter(_DAYS[localtime(s).tm_wday] for s in starts)
    found = []
    for counter in (slots, days):
        name, n = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
        if n / len(starts) >= limit("r5_pattern_share"):
            found.append(f"{n} of {len(starts)} waits started in {name}")
    return "; ".join(found) or None


def r5_waiting(report: Report) -> Result:
    t = report.totals
    recs: list[Recommendation] = []
    notes: list[str] = []
    needs = limit("r5_min_waits")
    if t.waits < needs:
        notes.append(not_enough("R5 (waits)", "waits", t.waits, needs))
    else:
        working = t.active_s + t.wait_s
        share = t.wait_s / working if working else 0.0
        if share >= limit("r5_wait_share"):
            starts = [m.start for m in report.marks if m.kind == "wait" and m.start is not None]
            pattern = _wait_pattern(starts)
            evidence = [
                f"{t.waits} waits took {fmt_dur(t.wait_s)}, {percent(share)} of active plus "
                "waiting time"
            ]
            if pattern:
                evidence.append(pattern)
            recs.append(
                Recommendation(
                    "R5",
                    "advice",
                    "Usage-limit waits cost a lot of elapsed time",
                    tuple(evidence),
                    "Start long runs just after a usage window resets, or let a second provider "
                    "take over when waiting matters more than the extra spend.",
                    f"waiting >= {limit('r5_wait_share') * 100:.0f}% of active plus waiting time",
                )
            )
    gates = [m.seconds for m in report.marks if m.kind == "gate_pause"]
    needs = limit("r5_min_gate_pauses")
    if len(gates) < needs:
        notes.append(not_enough("R5 (gates)", "pauses at gates", len(gates), needs))
    else:
        mid = median(gates) or 0.0
        if mid >= limit("r5_gate_median_s"):
            recs.append(
                Recommendation(
                    "R5",
                    "info",
                    "Runs sit at gates for a long time",
                    (
                        f"{len(gates)} gate pauses, median {fmt_dur(mid)}, "
                        f"total {fmt_dur(sum(gates))}",
                    ),
                    "If review gates are not catching anything, set low-risk phases to `auto`; "
                    "the choice is yours, this only shows the delay.",
                    f"median gate pause >= {fmt_dur(limit('r5_gate_median_s'))}",
                )
            )
    return recs, notes


def r6_timeouts(report: Report) -> Result:
    recs: list[Recommendation] = []
    notes: list[str] = []
    idle = [s for s in report.sessions if s.timed_out == "idle"]
    needs = limit("r6_min_idle_kills")
    limits = sorted({s.idle_timeout_s for s in idle if s.idle_timeout_s})
    if len(idle) >= needs:
        phases = {(s.project, s.phase) for s in idle}
        finished = sum(
            1 for r in report.phases if (r.project, r.phase) in phases and r.totals.phases_completed
        )
        if finished * 2 >= len(phases):
            shown = ", ".join(fmt_dur(v) for v in limits) or "unknown"
            recs.append(
                Recommendation(
                    "R6",
                    "advice",
                    "The idle timeout may be too tight",
                    (
                        f"{len(idle)} sessions were killed idle (limit {shown}); "
                        f"{finished} of those {len(phases)} phases then completed",
                    ),
                    "Raise `idle_timeout_s` in `.phx/config.toml` if these sessions were "
                    "working (a long test run emits no events), or keep it if they had hung.",
                    f"at least {needs:g} idle kills and half of those phases later completed",
                )
            )
    near = limit("r6_near_wall")
    capped = [
        s
        for s in report.sessions
        if s.timed_out == "wall" or (s.wall_timeout_s and s.duration_s >= near * s.wall_timeout_s)
    ]
    if capped:
        recs.append(
            Recommendation(
                "R6",
                "advice",
                "Sessions reached the wall-clock cap",
                tuple(
                    f"{s.project} {s.phase}: {fmt_dur(s.duration_s)} against a cap of "
                    f"{fmt_dur(s.wall_timeout_s or 0.0)}"
                    for s in capped[:5]
                ),
                "Split these phases, or raise `wall_timeout_s` in `.phx/config.toml`.",
                f"killed by the cap, or within {(1 - near) * 100:.0f}% of it",
            )
        )
    walls = [s.wall_timeout_s for s in report.sessions if s.wall_timeout_s]
    needs = limit("r6_min_sessions")
    if len(walls) < needs:
        notes.append(not_enough("R6 (wall cap)", "sessions", len(walls), needs))
    elif not capped:
        longest = max(s.duration_s for s in report.sessions if s.wall_timeout_s)
        cap = min(walls)
        if longest <= limit("r6_loose_wall") * cap:
            recs.append(
                Recommendation(
                    "R6",
                    "info",
                    "The wall-clock cap is far above any real session",
                    (f"longest of {len(walls)} sessions {fmt_dur(longest)}, cap {fmt_dur(cap)}",),
                    "A lower `wall_timeout_s` would stop a runaway session sooner.",
                    f"longest session <= {limit('r6_loose_wall') * 100:.0f}% of the cap",
                )
            )
    return recs, notes


def _rising(values: list[float | None]) -> bool:
    rise = 1 + limit("r7_rise")
    a, b, c = values
    return (
        a is not None
        and b is not None
        and c is not None
        and a > 0
        and b >= a * rise
        and (c >= b * rise)
    )


def r7_trend(report: Report) -> Result:
    needs = limit("r7_min_sessions")
    last = report.periods[-3:]
    usable = [p for p in last if p.totals.sessions >= needs]
    if len(usable) < 3:
        return [], [not_enough("R7", "periods usable", len(usable), 3)]
    recs = []
    for label, metric, show in (
        ("Cost per completed phase", "cost_per_phase", money),
        ("Non-completing share of cost", "noncompleting_cost_share", percent),
    ):
        values: list[float | None] = [getattr(p.totals, metric) for p in last]
        if _rising(values):
            recs.append(
                Recommendation(
                    "R7",
                    "advice",
                    f"{label} rose two periods in a row",
                    tuple(f"{p.label}: {show(v)}" for p, v in zip(last, values, strict=True)),
                    "Compare the phases in the last period with those before it: bigger phases "
                    "are fine, the same phases costing more are not.",
                    f"up at least {limit('r7_rise') * 100:.0f}% in each of two periods",
                )
            )
    return recs, []


def completion_rate(t: Totals) -> float | None:
    return 1 - t.noncompleting_sessions / t.sessions if t.sessions else None


def r8_providers(report: Report) -> Result:
    needs = limit("r8_min_sessions")
    rows = {k: t for k, t in sorted(report.by_provider.items()) if t.sessions >= needs}
    if len(rows) < 2:
        return [], [not_enough("R8", "providers with a fair sample", len(rows), 2)]
    rates = {k: completion_rate(t) or 0.0 for k, t in rows.items()}
    best, worst = max(rates, key=lambda k: rates[k]), min(rates, key=lambda k: rates[k])
    if rates[best] - rates[worst] < limit("r8_gap"):
        return [], []
    return [
        Recommendation(
            "R8",
            "info",
            f"Sessions complete more often on {best} than on {worst}",
            tuple(
                f"{k}: {percent(rates[k])} of {rows[k].sessions} sessions completed"
                for k in (best, worst)
            ),
            "The phases differed too, so treat this as a question, not a verdict.",
            f"completion rates at least {limit('r8_gap') * 100:.0f} points apart",
        )
    ], []


RULES: tuple[Callable[[Report], Result], ...] = (
    r1_cost_concentration,
    r2_noncompleting,
    r3_model_fit,
    r4_cache,
    r5_waiting,
    r6_timeouts,
    r7_trend,
    r8_providers,
)


def evaluate(report: Report) -> Result:
    recs: list[Recommendation] = []
    notes: list[str] = []
    for rule in RULES:
        fired, said = rule(report)
        recs += fired
        notes += said
    return recs, notes
