"""Operational decorators.

- ``@fail_soft`` turns network/auth/5xx failures into structured envelopes
  (``{"status": "unreachable" | "denied", ...}``) instead of raised exceptions.
  Config/validation/programming errors still raise.
- ``@requires_writes`` marks a tool as mutating; the registry refuses to
  register it unless ``SL_ENABLE_WRITES=true``.
- ``record_evidence`` writes a redacted successful response to disk atomically.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import ssl
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .errors import ForbiddenError, ServerError, SLAPIError, TransportError
from .logging import redact

if TYPE_CHECKING:
    from .registry import ServerContext

logger = logging.getLogger(__name__)

_REQUIRES_WRITES_ATTR = "_sl_requires_writes"
_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def requires_writes(fn: Callable[..., Any]) -> Callable[..., Any]:
    setattr(fn, _REQUIRES_WRITES_ATTR, True)
    return fn


def is_write_tool(fn: Callable[..., Any]) -> bool:
    return bool(getattr(fn, _REQUIRES_WRITES_ATTR, False))


def fail_soft(ctx: ServerContext) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                return _unreachable(tool_name, exc)
            except ssl.SSLError as exc:
                return _unreachable(tool_name, exc)
            except TransportError as exc:
                return _unreachable(tool_name, exc)
            except ServerError as exc:
                return _unreachable(tool_name, exc, status_code=exc.status_code)
            except ForbiddenError as exc:
                return _denied(tool_name, exc)
            except SLAPIError:
                raise

            if ctx.settings.sl_evidence_dir:
                try:
                    record_evidence(ctx.settings.sl_evidence_dir, tool_name, result)
                except OSError as exc:
                    logger.warning(
                        "failed to write evidence file",
                        extra={"tool": tool_name, "error": str(exc)},
                    )
            return result

        return wrapper

    return decorator


def _unreachable(tool_name: str, exc: BaseException, *, status_code: int | None = None) -> dict:
    payload: dict[str, Any] = {
        "status": "unreachable",
        "tool": tool_name,
        "error_class": type(exc).__name__,
        "error": str(exc),
    }
    if status_code is not None:
        payload["status_code"] = status_code
    logger.info("fail-soft: unreachable", extra={"tool": tool_name})
    return payload


def _denied(tool_name: str, exc: ForbiddenError) -> dict:
    logger.info("fail-soft: denied", extra={"tool": tool_name, "status_code": exc.status_code})
    return {
        "status": "denied",
        "tool": tool_name,
        "status_code": exc.status_code,
        "error": str(exc),
    }


def _sanitize_filename(name: str) -> str:
    return "".join(c if c in _SAFE_NAME_CHARS else "_" for c in name)[:120] or "tool"


def record_evidence(evidence_dir: str, tool_name: str, payload: Any) -> Path:
    target_dir = Path(evidence_dir)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")
    suffix = f"{int(time.monotonic() * 1_000_000) % 1_000_000:06d}"
    final_path = target_dir / f"{ts}_{_sanitize_filename(tool_name)}_{suffix}.json"
    redacted = redact({"result": payload})["result"]
    fd, tmp_name = tempfile.mkstemp(prefix=".sl-evidence-", dir=str(target_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(redacted, handle, default=str, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, final_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return final_path
