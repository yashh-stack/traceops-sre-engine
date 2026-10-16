"""
Jev Non-Autoregressive Edge Telemetry Guard & Token Repair Engine.
Sub-15ms deterministic triage layer for OpenTelemetry span waterfalls and error ASTs.
"""
from __future__ import annotations
import json
import re
import logging
from typing import Any, Dict

logger = logging.getLogger("traceops.jev_triage")

class JevTelemetryGuard:
    """
    Tier-1 Non-Autoregressive Telemetry Guard.
    Performs deterministic, microsecond-latency evaluation of raw OpenTelemetry spans,
    suppressing normal baseline traffic and triaging only actionable anomalies.
    """

    def __init__(self, p99_latency_ms: float = 500.0):
        self.p99_latency_ms = p99_latency_ms
        # Precompiled regex patterns for zero-alloc matching
        self._error_status_pattern = re.compile(r"^(5\d{2}|429|ERROR|CRITICAL)$", re.IGNORECASE)
        self._exception_pattern = re.compile(r"(exception|traceback|panic|oom|deadlock|timeout|segfault)", re.IGNORECASE)

    def evaluate_span(self, span_payload: Dict[str, Any]) -> bool:
        """
        Evaluate a single OpenTelemetry span payload in sub-15ms.
        Returns True strictly when:
        1. HTTP status code is 5xx or rate-limited 429.
        2. Execution duration/latency exceeds the p99 threshold.
        3. Error flag is explicitly True or span contains unhandled exception attributes.
        """
        if not isinstance(span_payload, dict):
            return False

        # 1. Latency check (support ms and duration calculations)
        duration_ms = span_payload.get("duration_ms")
        if duration_ms is None:
            duration = span_payload.get("duration")
            if duration is not None:
                duration_ms = float(duration)
        if duration_ms is not None and float(duration_ms) >= self.p99_latency_ms:
            logger.debug(f"[JEV] Flagged span: latency {duration_ms}ms >= {self.p99_latency_ms}ms")
            return True

        # 2. HTTP Status Code check
        status_code = span_payload.get("http_status_code") or span_payload.get("status_code") or span_payload.get("http.status_code")
        if status_code is not None:
            if self._error_status_pattern.match(str(status_code)):
                logger.debug(f"[JEV] Flagged span: error status code {status_code}")
                return True

        # 3. Explicit error status
        status = span_payload.get("status")
        if isinstance(status, dict):
            code = status.get("code")
            if str(code).upper() in {"ERROR", "STATUS_CODE_ERROR", "2"}:
                return True
        elif isinstance(status, str) and self._error_status_pattern.match(status):
            return True

        # 4. Error flag / message check
        if span_payload.get("error") is True or span_payload.get("is_error") is True:
            return True

        error_message = span_payload.get("error_message") or span_payload.get("status_message") or ""
        if error_message and self._exception_pattern.search(str(error_message)):
            logger.debug(f"[JEV] Flagged span: matched exception pattern in message")
            return True

        # 5. Attributes introspection
        attributes = span_payload.get("attributes", {})
        if isinstance(attributes, dict):
            for key, val in attributes.items():
                if "error" in key.lower() or "exception" in key.lower():
                    if val is True or (isinstance(val, str) and self._exception_pattern.search(val)):
                        return True

        return False

    @staticmethod
    def repair_json_tokens(raw_output: str) -> str:
        """
        Fast 1-step non-autoregressive token repair infiller.
        Repairs truncated or streaming JSON payloads from LLMs:
        - Strips markdown code fences.
        - Fixes unclosed string literals.
        - Removes trailing commas before closing tokens.
        - Closes unclosed braces and brackets.
        """
        if not raw_output or not raw_output.strip():
            return "{}"

        text = raw_output.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # If already valid JSON, return immediately
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        # 1. Fix unclosed strings
        # Count unescaped quotes
        in_string = False
        escape = False
        fixed_chars = []
        for char in text:
            if char == '\\' and not escape:
                escape = True
                fixed_chars.append(char)
                continue
            if char == '"' and not escape:
                in_string = not in_string
            fixed_chars.append(char)
            escape = False

        if in_string:
            fixed_chars.append('"')

        repaired = "".join(fixed_chars)

        # 2. Remove trailing commas before closing braces/brackets
        repaired = re.sub(r",\s*([\]}])", r"\1", repaired)

        # 3. Balance unclosed brackets and braces
        open_stack = []
        in_str = False
        esc = False
        for char in repaired:
            if char == '\\' and not esc:
                esc = True
                continue
            if char == '"' and not esc:
                in_str = not in_str
            if not in_str:
                if char in "{[":
                    open_stack.append(char)
                elif char == "}":
                    if open_stack and open_stack[-1] == "{":
                        open_stack.pop()
                elif char == "]":
                    if open_stack and open_stack[-1] == "[":
                        open_stack.pop()
            esc = False

        # Close open containers in LIFO order
        for token in reversed(open_stack):
            if token == "{":
                repaired += "}"
            elif token == "[":
                repaired += "]"

        # Final verification
        try:
            json.loads(repaired)
            return repaired
        except Exception:
            # Fallback wrapper if still malformed
            return json.dumps({"raw_fragment": text, "repaired": False})
