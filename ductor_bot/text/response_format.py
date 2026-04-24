"""Shared formatting primitives for command response text."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ductor_bot.i18n import t

SEP = "\u2500\u2500\u2500"

_SHELL_TOOLS = frozenset({"bash", "powershell", "cmd", "sh", "zsh", "shell"})
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_tool_name(name: str) -> str:
    """Normalize shell-related tool names to 'Shell' for display."""
    return "Shell" if name.lower() in _SHELL_TOOLS else name


def _sentence_case(text: str) -> str:
    """Upper-case the first character while leaving the rest untouched."""
    return text[:1].upper() + text[1:] if text else text


def _prettify_identifier(value: str) -> str:
    """Convert camelCase/snake_case tool names into lower-case readable text."""
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", value.replace("_", " ").replace("-", " "))
    return " ".join(spaced.split()).lower()


def _tool_activity_phrase(name: str) -> str | None:
    """Return a lower-case human label for a tool call."""
    clean = name.strip()
    if not clean:
        return None

    normalized = normalize_tool_name(clean)
    key = _NON_ALNUM_RE.sub("", normalized.lower())
    label_key: str | None = None
    if key == "shell":
        label_key = "footer.action_running_shell"
    elif key in {"edit", "write", "filechange", "multiedit", "strreplace", "applypatch"}:
        label_key = "footer.action_editing_files"
    elif key in {"read", "view", "cat", "glob", "ls", "listdir", "listfiles"}:
        label_key = "footer.action_reading_files"
    elif key == "websearch":
        label_key = "footer.action_searching_web"
    elif key in {"todowrite", "todolist", "todolistwrite", "updateplan"}:
        label_key = "footer.action_updating_plan"

    if label_key is not None:
        return t(label_key)

    pretty = _prettify_identifier(normalized)
    return t("footer.action_using_tool", tool=pretty) if pretty else None


def tool_activity_text(name: str) -> str:
    """Return a sentence-case label for live tool activity."""
    phrase = _tool_activity_phrase(name)
    return _sentence_case(phrase) if phrase else ""


def tool_activity_summary(name: str) -> str | None:
    """Return a lower-case summary label for action-footers."""
    return _tool_activity_phrase(name)


def _system_status_phrase(status: str | None) -> str | None:
    """Return a lower-case human label for a raw system status token."""
    if status is None:
        return None

    clean = status.strip()
    if not clean:
        return None

    known = {
        "thinking": t("footer.action_thinking"),
        "compacting": t("footer.action_compacting_context"),
        "recovering": t("footer.action_recovering_session"),
        "timeout_warning": t("footer.action_approaching_timeout"),
        "timeout_extended": t("footer.action_extended_timeout"),
    }
    if clean in known:
        return known[clean]

    pretty = _prettify_identifier(clean)
    return pretty or None


def system_status_text(status: str | None) -> str | None:
    """Return a sentence-case label for live system status text."""
    phrase = _system_status_phrase(status)
    return _sentence_case(phrase) if phrase else None


def system_status_summary(status: str | None) -> str | None:
    """Return a lower-case summary label for action-footers."""
    if status == "thinking":
        return None
    return _system_status_phrase(status)


def format_action_footer(actions: Sequence[tuple[str, int]]) -> str:
    """Format a terse final action trace footer."""
    if not actions:
        return ""

    rendered = ", ".join(f"{name} x{count}" if count > 1 else name for name, count in actions)
    return "\n---\n" + t("footer.actions", actions=rendered)


def fmt(*blocks: str) -> str:
    """Join non-empty blocks with double newlines."""
    return "\n\n".join(b for b in blocks if b)


# Known CLI error patterns -> user-friendly short explanation.
_AUTH_PATTERNS = (
    "401",
    "unauthorized",
    "authentication",
    "signing in again",
    "sign in again",
    "token has been",
)
_RATE_PATTERNS = ("429", "rate limit", "too many requests", "quota exceeded")
_CONTEXT_PATTERNS = ("context length", "token limit", "maximum context", "too long")


def classify_cli_error(raw: str) -> str | None:
    """Return a user-facing hint for known CLI error patterns, or None."""
    lower = raw.lower()
    if any(p in lower for p in _AUTH_PATTERNS):
        return t("session.error_auth")
    if any(p in lower for p in _RATE_PATTERNS):
        return t("session.error_rate")
    if any(p in lower for p in _CONTEXT_PATTERNS):
        return t("session.error_context")
    return None


def session_error_text(model: str, cli_detail: str = "") -> str:
    """Build the error message shown to the user on CLI failure."""
    base = fmt(t("session.error_header"), SEP, t("session.error_body", model=model))
    hint = classify_cli_error(cli_detail) if cli_detail else None
    if hint:
        return fmt(base, t("session.error_cause", hint=hint))
    if cli_detail:
        # Show first meaningful line, truncated.
        detail = cli_detail.strip().split("\n")[0][:200]
        return fmt(base, t("session.error_detail", detail=detail))
    return base


def timeout_error_text(model: str, timeout_seconds: float) -> str:
    """Build the error message shown when the CLI times out."""
    minutes = int(timeout_seconds / 60)
    return fmt(
        t("timeout.error_header"), SEP, t("timeout.error_body", model=model, minutes=minutes)
    )


def new_session_text(provider: str) -> str:
    """Build /new response for provider-local reset."""
    provider_label = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}.get(
        provider.lower(), provider
    )
    return fmt(
        t("session.reset_header"),
        SEP,
        t("session.reset_body", provider=provider_label),
    )


def stop_text(killed: bool, provider: str) -> str:
    """Build the /stop response."""
    body = t("stop.killed", provider=provider) if killed else t("stop.nothing")
    return fmt(t("stop.header"), SEP, body)


# -- Timeout messages --


def timeout_warning_text(remaining: float) -> str:
    """Warning text shown when a timeout is approaching."""
    if remaining >= 60:
        mins = int(remaining // 60)
        return t("timeout.warning_minutes", mins=mins)
    secs = int(remaining)
    return t("timeout.warning_seconds", secs=secs)


def timeout_extended_text(extension: float, remaining_ext: int) -> str:
    """Notification that the timeout was extended due to activity."""
    secs = int(extension)
    return t("timeout.extended", secs=secs, remaining=remaining_ext)


def timeout_result_text(elapsed: float, configured: float) -> str:
    """Error text when a CLI process hit its timeout."""
    return fmt(
        t("timeout.result_header"),
        SEP,
        t("timeout.result_body", elapsed=int(elapsed), configured=int(configured)),
    )


# -- Startup lifecycle messages --


def startup_notification_text(kind: str) -> str:
    """Notification text for startup events.

    Only ``first_start`` and ``system_reboot`` produce output.
    ``service_restart`` is silent (handled by the existing sentinel system).
    """
    if kind == "first_start":
        return fmt(t("startup.first_start_header"), SEP, t("startup.first_start_body"))
    if kind == "system_reboot":
        return fmt(t("startup.reboot_header"), SEP, t("startup.reboot_body"))
    return ""


# -- Auto-recovery messages --


def format_technical_footer(
    model_name: str,
    total_tokens: int,
    input_tokens: int,
    cost_usd: float,
    duration_ms: float | None,
) -> str:
    """Format technical metadata as a footer line."""
    output_tokens = total_tokens - input_tokens
    parts = [t("footer.model", name=model_name)]
    parts.append(t("footer.tokens", total=total_tokens, input=input_tokens, output=output_tokens))
    if cost_usd > 0:
        parts.append(t("footer.cost", cost=f"{cost_usd:.4f}"))
    if duration_ms is not None:
        secs = duration_ms / 1000
        parts.append(t("footer.time", secs=f"{secs:.1f}"))
    return "\n---\n" + " | ".join(parts)


def recovery_notification_text(
    kind: str,
    prompt_preview: str,
    session_name: str = "",
) -> str:
    """Notification that interrupted work is being recovered."""
    preview = prompt_preview[:80] + ("…" if len(prompt_preview) > 80 else "")
    if kind == "named_session":
        return fmt(
            t("recovery.named_header"),
            SEP,
            t("recovery.named_body", session=session_name, preview=preview),
        )
    return fmt(
        t("recovery.interrupted_header"),
        SEP,
        t("recovery.interrupted_body", preview=preview),
    )
