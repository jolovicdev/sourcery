from __future__ import annotations

from collections.abc import Sequence
import time
from typing import Any

from sourcery.exceptions import ErrorContext, RuntimeIntegrationError, SourceryPausedRunError
from sourcery.runtime.errors import is_rate_limit_message, is_transient_message
from sourcery.runtime.blackgeorge_protocols import BlackGeorgeRetryRuntime


class BlackGeorgeRetryMixin:
    def _resume_report_with_desk(
        self: BlackGeorgeRetryRuntime,
        *,
        report: Any,
        context: ErrorContext,
    ) -> Any:
        if report.status != "paused":
            return report

        if not self._retry.auto_resume_paused_runs:
            raise SourceryPausedRunError("Run paused and auto-resume is disabled", context=context)

        resumes = 0
        current = report
        while current.status == "paused":
            resumes += 1
            if resumes > self._retry.max_pause_resumes:
                raise SourceryPausedRunError(
                    "Run stayed paused after max resume attempts",
                    context=context,
                )
            pending_action = getattr(current, "pending_action", None)
            if pending_action is None:
                raise SourceryPausedRunError("Run paused without pending action", context=context)
            action_type = getattr(pending_action, "type", "")
            decision_or_input: Any = True if action_type == "confirmation" else ""
            try:
                current = self._desk.resume(
                    current,
                    decision_or_input,
                    stream=self._runtime_config.stream,
                )
            except Exception as exc:
                raise RuntimeIntegrationError(str(exc), context=context) from exc
        return current

    def _resume_if_paused(
        self: BlackGeorgeRetryRuntime,
        *,
        flow: Any,
        report: Any,
        context: ErrorContext,
    ) -> Any:
        if report.status != "paused":
            return report

        if not self._retry.auto_resume_paused_runs:
            raise SourceryPausedRunError("Run paused and auto-resume is disabled", context=context)

        resumes = 0
        current = report
        while current.status == "paused":
            resumes += 1
            if resumes > self._retry.max_pause_resumes:
                raise SourceryPausedRunError(
                    "Run stayed paused after max resume attempts",
                    context=context,
                )
            pending_action = getattr(current, "pending_action", None)
            if pending_action is None:
                raise SourceryPausedRunError("Run paused without pending action", context=context)
            action_type = getattr(pending_action, "type", "")
            decision_or_input: Any = True if action_type == "confirmation" else ""
            try:
                current = flow.resume(
                    current,
                    decision_or_input,
                    stream=self._runtime_config.stream,
                )
            except Exception as exc:
                raise RuntimeIntegrationError(str(exc), context=context) from exc
        return current

    def _should_retry_errors(self: BlackGeorgeRetryRuntime, errors: Sequence[str]) -> bool:
        if self._retry.retry_on_rate_limit and any(
            is_rate_limit_message(error) for error in errors
        ):
            return True
        if self._retry.retry_on_transient_errors and any(
            is_transient_message(error) for error in errors
        ):
            return True
        return False

    def _should_retry_exception(self: BlackGeorgeRetryRuntime, exc: Exception) -> bool:
        message = str(exc)
        if self._retry.retry_on_rate_limit and is_rate_limit_message(message):
            return True
        if self._retry.retry_on_transient_errors and is_transient_message(message):
            return True
        return False

    def _sleep_before_retry(self: BlackGeorgeRetryRuntime, attempt: int) -> None:
        delay = min(
            self._retry.initial_backoff_seconds
            * (self._retry.backoff_multiplier ** max(attempt - 1, 0)),
            self._retry.max_backoff_seconds,
        )
        if delay > 0:
            time.sleep(delay)
