"""Desktop notifications through ``notify-send`` (spec A9, task 6 of Phase 07).

Silent by design: every notification carries the ``suppress-sound`` hint and PHX never
speaks (no Prometheus). Without a display or session bus, or without ``notify-send``,
it degrades to a log line. Every attempt is logged as a ``notify`` event.
"""

import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from phx.logging import EventLog

APP_NAME = "phx"
TIMEOUT_S = 5

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Note:
    kind: str  # phase_complete, blocked, waiting, provider_switch, finished, failed, paused
    title: str
    body: str
    urgency: str = "normal"  # low | normal | critical


class Notifier:
    def __init__(
        self,
        log: EventLog,
        *,
        env: Mapping[str, str],
        repo_label: str,
        run: Runner = subprocess.run,
    ) -> None:
        self.log = log
        self.env = dict(env)
        self.repo_label = repo_label
        self._run = run
        self.sent: list[Note] = []

    def _unavailable(self) -> str | None:
        if not (self.env.get("WAYLAND_DISPLAY") or self.env.get("DISPLAY")):
            return "no display"
        if not self.env.get("DBUS_SESSION_BUS_ADDRESS") and not self.env.get("XDG_RUNTIME_DIR"):
            return "no session bus"
        if shutil.which("notify-send", path=self.env.get("PATH")) is None:
            return "notify-send not found"
        return None

    def send(self, note: Note, *, phase: str | None = None) -> bool:
        self.sent.append(note)
        title = f"PHX {self.repo_label}: {note.title}"
        why = self._unavailable()
        sent = False
        if why is None:
            argv = [
                "notify-send",
                f"--app-name={APP_NAME}",
                f"--urgency={note.urgency}",
                "--hint=boolean:suppress-sound:true",
                title,
                note.body,
            ]
            try:
                got = self._run(
                    argv, capture_output=True, text=True, timeout=TIMEOUT_S, env=self.env
                )
                sent = got.returncode == 0
                why = None if sent else f"notify-send exited {got.returncode}"
            except (OSError, subprocess.SubprocessError) as exc:
                why = f"notify-send failed: {type(exc).__name__}"
        self.log.event(
            "notify",
            phase=phase,
            reason=note.title,
            kind=note.kind,
            body=note.body,
            sent=sent,
            skipped=why,
        )
        return sent


# --------------------------------------------------------------------------- message builders


def phase_complete(phase: str, detail: str) -> Note:
    return Note("phase_complete", f"phase {phase} complete", detail, "low")


def blocked(
    repo: str, phase: str, question_ids: tuple[str, ...], reason: str, summary: str | None
) -> Note:
    qs = ", ".join(f"#{q}" for q in question_ids) or "?"
    first = question_ids[0] if question_ids else "N"
    answer = f'Answer: phx answer {repo} {first} "<answer>", then: phx resume {repo}'
    body = "\n\n".join((summary or reason, answer))
    return Note("blocked", f"phase {phase} blocked on question {qs}", body, "critical")


def waiting(phase: str, reason: str, resume_at: str) -> Note:
    return Note(
        "waiting",
        f"usage limit, waiting (phase {phase})",
        f"{reason}\nResuming around {resume_at}. Switch to OpenRouter (Super+Alt+A) to resume now.",
    )


def provider_switch(phase: str, provider: str) -> Note:
    return Note(
        "provider_switch",
        f"provider switched to {provider}",
        f"Resuming phase {phase} now on {provider}.",
    )


def verification_failed(phase: str, reason: str, summary: str | None) -> Note:
    return Note("failed", f"phase {phase} needs attention", summary or reason, "critical")


def paused(repo: str, phase: str | None, reason: str, summary: str | None = None) -> Note:
    where = f"phase {phase}" if phase else "run"
    body = (summary or reason) + f"\n\nWhen ready: phx resume {repo}"
    return Note("paused", f"{where} paused", body)


def finished(detail: str) -> Note:
    return Note("finished", "run finished", detail)
