from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast
import zlib

from pydantic import BaseModel

from sourcery.contracts import AlignedExtraction, DocumentResult
from sourcery.io.jsonl import load_document_results_jsonl

try:
    from IPython import get_ipython  # type: ignore[import-not-found]
    from IPython.display import HTML  # type: ignore[import-not-found]
except Exception:
    get_ipython = None
    HTML = None


def _is_notebook() -> bool:
    if get_ipython is None:
        return False
    try:
        shell = get_ipython()
        if shell is None:
            return False
        return cast(bool, shell.__class__.__name__ != "TerminalInteractiveShell")
    except Exception:
        return False


def _color_for_entity(entity: str) -> str:
    palette = [
        "#d2f4ea",
        "#ffe5b4",
        "#d7e3fc",
        "#f9d5e5",
        "#fef3bd",
        "#d8f3dc",
        "#f8d6cc",
        "#e7d8ff",
        "#d4f1f4",
    ]
    return palette[zlib.crc32(entity.encode("utf-8")) % len(palette)]


def _sorted_extractions(document: DocumentResult) -> list[AlignedExtraction]:
    valid = [
        extraction
        for extraction in document.extractions
        if extraction.alignment_status != "unresolved"
        and extraction.char_start < extraction.char_end
    ]
    return sorted(valid, key=lambda extraction: (extraction.char_start, extraction.char_end))


def _highlighted_text(document: DocumentResult, extractions: list[AlignedExtraction]) -> str:
    text = document.text
    points: list[tuple[int, int, str]] = []
    for index, extraction in enumerate(extractions):
        color = _color_for_entity(extraction.entity)
        points.append(
            (
                extraction.char_start,
                1,
                f"<mark class='sx-highlight' data-idx='{index}' style='background:{color};'>",
            )
        )
        points.append((extraction.char_end, 0, "</mark>"))

    points.sort(key=lambda item: (item[0], item[1]))

    result: list[str] = []
    cursor = 0
    for position, _, tag in points:
        if position > cursor:
            result.append(html.escape(text[cursor:position]))
        result.append(tag)
        cursor = position

    if cursor < len(text):
        result.append(html.escape(text[cursor:]))

    return "".join(result)


def _legend(extractions: list[AlignedExtraction]) -> str:
    by_entity: dict[str, str] = {}
    for index, extraction in enumerate(extractions):
        by_entity.setdefault(extraction.entity, _color_for_entity(extraction.entity))

    if not by_entity:
        return ""

    tags = [
        f"<span class='sx-tag' style='background:{color}'>{html.escape(entity)}</span>"
        for entity, color in sorted(by_entity.items())
    ]
    return "<div class='sx-legend'><strong>Legend:</strong> " + " ".join(tags) + "</div>"


def _attr_dict(extraction: AlignedExtraction) -> dict[str, Any]:
    attrs = extraction.attributes
    if isinstance(attrs, BaseModel):
        return attrs.model_dump(mode="json")
    return dict(attrs)


def _interactive_html(
    document: DocumentResult, *, animation_speed: float, show_legend: bool
) -> str:
    if not document.text:
        return "<div class='sx-wrapper'><p>No text to visualize.</p></div>"

    extractions = _sorted_extractions(document)
    if not extractions:
        return "<div class='sx-wrapper'><p>No resolved extractions to visualize.</p></div>"

    highlighted = _highlighted_text(document, extractions)
    legend_html = _legend(extractions) if show_legend else ""

    payload = []
    for index, extraction in enumerate(extractions):
        payload.append(
            {
                "idx": index,
                "entity": extraction.entity,
                "text": extraction.text,
                "alignment": extraction.alignment_status,
                "confidence": extraction.confidence,
                "char_start": extraction.char_start,
                "char_end": extraction.char_end,
                "attributes": _attr_dict(extraction),
            }
        )

    payload_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")

    return (
        "<style>"
        ".sx-wrapper{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:10px 0;}"
        ".sx-panel{border:1px solid #d8dee8;border-radius:10px;padding:10px;background:#fbfdff;margin-bottom:10px;}"
        ".sx-legend{margin-bottom:8px;font-size:12px;color:#3b4252;}"
        ".sx-tag{display:inline-block;padding:2px 6px;border-radius:6px;margin-right:6px;color:#1d2433;font-size:11px;}"
        ".sx-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}"
        ".sx-btn{border:1px solid #c3d0e0;background:#eaf2ff;color:#1f3556;border-radius:8px;padding:5px 10px;cursor:pointer;font-size:12px;}"
        ".sx-btn:hover{background:#dbe8fb;}"
        ".sx-slider{width:280px;max-width:100%;}"
        ".sx-meta{font-size:12px;color:#4c566a;}"
        ".sx-attrs{font-size:12px;background:#f4f8ff;border-radius:8px;padding:8px;margin-top:8px;white-space:pre-wrap;}"
        ".sx-text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;"
        "border:1px solid #d8dee8;border-radius:10px;padding:12px;max-height:360px;overflow:auto;line-height:1.5;}"
        ".sx-highlight{border-radius:4px;padding:1px 1px;}"
        ".sx-current{outline:2px solid #1f3556;}"
        "</style>"
        "<div class='sx-wrapper'>"
        f"<div class='sx-panel'>{legend_html}"
        "<div class='sx-controls'>"
        "<button class='sx-btn' data-action='prev'>Prev</button>"
        "<button class='sx-btn' data-action='play'>Play</button>"
        "<button class='sx-btn' data-action='next'>Next</button>"
        f"<input class='sx-slider' data-action='jump' type='range' min='0' max='{max(len(payload) - 1, 0)}' value='0'/>"
        "<span class='sx-meta' data-role='meta'></span>"
        "</div>"
        "<div class='sx-attrs' data-role='attrs'></div>"
        "</div>"
        f"<div class='sx-text'>{highlighted}</div>"
        "</div>"
        "<script>"
        "(function(){"
        f"const data={payload_json};"
        f"const speed={max(animation_speed, 0.15)}*1000;"
        "const wrappers=document.querySelectorAll('.sx-wrapper');"
        "const root=wrappers[wrappers.length-1];"
        "const marks=Array.from(root.querySelectorAll('.sx-highlight'));"
        "const slider=root.querySelector('.sx-slider');"
        "const attrs=root.querySelector('[data-role=attrs]');"
        "const meta=root.querySelector('[data-role=meta]');"
        "let idx=0;"
        "let timer=null;"
        "let playing=false;"
        "function render(){"
        "if(!data.length){return;}"
        "marks.forEach(m=>m.classList.remove('sx-current'));"
        "const m=root.querySelector(`.sx-highlight[data-idx='${idx}']`);"
        "if(m){m.classList.add('sx-current');m.scrollIntoView({block:'center',behavior:'smooth'});}"
        "slider.value=String(idx);"
        "const item=data[idx];"
        "meta.textContent=`${idx+1}/${data.length} | ${item.entity} | ${item.char_start}-${item.char_end}`;"
        "attrs.textContent=JSON.stringify({text:item.text,alignment:item.alignment,confidence:item.confidence,attributes:item.attributes},null,2);"
        "}"
        "function next(){idx=(idx+1)%data.length;render();}"
        "function prev(){idx=(idx-1+data.length)%data.length;render();}"
        "function sxNext(){next();}"
        "function sxPrev(){prev();}"
        "function sxJump(){idx=Number(slider.value||0);render();}"
        "function sxPlayPause(){const btn=root.querySelector('[data-action=play]');"
        "if(!playing){timer=setInterval(next,speed);playing=true;btn.textContent='Pause';}"
        "else{clearInterval(timer);timer=null;playing=false;btn.textContent='Play';}"
        "}"
        "root.querySelector('[data-action=prev]').onclick=sxPrev;"
        "root.querySelector('[data-action=play]').onclick=sxPlayPause;"
        "root.querySelector('[data-action=next]').onclick=sxNext;"
        "slider.oninput=sxJump;"
        "render();"
        "})();"
        "</script>"
    )


def render_document_html(document: DocumentResult) -> str:
    return _interactive_html(document, animation_speed=1.0, show_legend=True)


def write_document_html(document: DocumentResult, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html_document = (
        "<html><head><meta charset='utf-8'><title>Sourcery Visualization</title></head><body>"
        + render_document_html(document)
        + "</body></html>"
    )
    path.write_text(html_document, encoding="utf-8")


def visualize(
    data_source: DocumentResult | str | Path,
    *,
    animation_speed: float = 1.0,
    show_legend: bool = True,
    return_html_obj: bool = True,
) -> str | Any:
    if isinstance(data_source, (str, Path)):
        documents = load_document_results_jsonl(data_source)
        if not documents:
            raise ValueError(f"No documents found in: {data_source}")
        document = documents[0]
    else:
        document = data_source

    html_content = _interactive_html(
        document, animation_speed=animation_speed, show_legend=show_legend
    )
    if return_html_obj and HTML is not None and _is_notebook():
        return HTML(html_content)
    return html_content
