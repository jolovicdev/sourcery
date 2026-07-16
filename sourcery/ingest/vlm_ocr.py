from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from sourcery.contracts import RuntimeConfig
from sourcery.exceptions import SourceryIngestionError


@runtime_checkable
class VLMOCRBackend(Protocol):
    def extract_text(self, *, image_path: Path, prompt: str | None = None) -> str: ...


class BlackGeorgeVLMOCRBackend:
    def __init__(
        self,
        runtime: RuntimeConfig,
        *,
        default_prompt: str = "Extract all text from this image exactly as it appears.",
    ) -> None:
        self._runtime = runtime
        self._default_prompt = default_prompt

    def extract_text(self, *, image_path: Path, prompt: str | None = None) -> str:
        import blackgeorge

        if not image_path.is_file():
            raise SourceryIngestionError(f"Image file does not exist: {image_path}")
        resolved_prompt = prompt or self._default_prompt
        image_uri = blackgeorge.encode_file(str(image_path))
        worker = blackgeorge.Worker(
            name="vlm-ocr",
            instructions=resolved_prompt,
        )
        job = blackgeorge.Job(
            input=[
                {"type": "image_url", "image_url": {"url": image_uri}},
                {"type": "text", "text": resolved_prompt},
            ],
        )
        desk = blackgeorge.Desk(
            model=self._runtime.model,
            temperature=self._runtime.temperature,
            max_tokens=self._runtime.max_tokens,
            respect_context_window=self._runtime.respect_context_window,
            storage_dir=self._runtime.storage_dir,
        )
        try:
            report = desk.run(worker, job)
        finally:
            desk.close()
        if report.status != "completed":
            errors = "; ".join(report.errors) or f"run status was {report.status}"
            raise SourceryIngestionError(f"VLM OCR failed for {image_path.name}: {errors}")
        content = report.content
        if content:
            return content.strip()
        raise SourceryIngestionError(
            f"VLM OCR produced empty text for {image_path.name}"
            + (f" ({'; '.join(report.errors)})" if report.errors else "")
        )
