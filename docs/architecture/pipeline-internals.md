# Pipeline Internals

Pipeline modules are deterministic and side-effect free.

## `chunking.py`

Responsibilities:

- Segment document text into stable chunk windows.
- Preserve global offsets (`char_start`, `char_end`) in each `TextChunk`.
- Attach optional previous context for continuity.

Key operational knobs from `ExtractOptions`:

- `max_chunk_chars`
- `context_window_chars`

`plan_chunks(...)` receives `pass_id` for chunk identity; pass iteration (`max_passes`) is controlled by `SourceryEngine`.

## `prompt_compiler.py`

Responsibilities:

- Build system/user prompt envelopes for runtime workers.
- Serialize entity schema and examples into a stable payload format.
- Inject pass/chunk context.

Output primitive:

- `PromptEnvelope(system, user, schema_payload)`

## `aligner.py`

Responsibilities:

- Map runtime `ExtractionCandidate` values back onto source text.
- Produce `AlignedExtraction` with offsets and alignment status.

Resolution strategy:

1. Exact span match
2. Fuzzy match (optional)
3. Partial exact fallback (optional)
4. Unresolved when match fails

## `merger.py`

Responsibilities:

- Merge aligned extractions per document.
- Resolve overlaps deterministically.

Winner precedence favors stronger grounding and stable ordering to maintain reproducibility across runs.

## `example_validator.py`

Responsibilities:

- Validate that each example extraction is alignable in its example text.
- Emit issues with statuses (`fuzzy`, `unresolved`) when exact span matching fails.
- Raise `ExampleValidationError` when strict mode requires it.
