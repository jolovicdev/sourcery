from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from sourcery.contracts import DocumentResult
from sourcery.io.jsonl import load_document_results_jsonl


def _sorted_extractions(document: DocumentResult) -> list[Any]:
    return sorted(
        [
            extraction
            for extraction in document.extractions
            if extraction.alignment_status != "unresolved"
            and extraction.char_start < extraction.char_end
        ],
        key=lambda extraction: (
            extraction.char_start,
            extraction.char_end,
            extraction.entity,
            extraction.text,
        ),
    )


def _attr_dict(extraction: Any) -> dict[str, Any]:
    attrs = extraction.attributes
    if hasattr(attrs, "model_dump"):
        try:
            dumped = attrs.model_dump(mode="json")
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return dict(attrs)


def _color_for_entity(entity: str, index: int) -> str:
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
    seed = abs(hash(entity)) % len(palette)
    return palette[(seed + index) % len(palette)]


def _highlighted_text(document: DocumentResult, payload: list[dict[str, Any]]) -> str:
    text = document.text
    points: list[tuple[int, int, str]] = []
    for extraction in payload:
        points.append(
            (
                int(extraction["char_start"]),
                1,
                (
                    "<mark class='sr-highlight' "
                    f"data-idx='{int(extraction['idx'])}' "
                    f"style='background:{extraction['color']};'>"
                ),
            )
        )
        points.append((int(extraction["char_end"]), 0, "</mark>"))

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


def _build_payload(document: DocumentResult) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for index, extraction in enumerate(_sorted_extractions(document)):
        payload.append(
            {
                "idx": index,
                "entity": extraction.entity,
                "text": extraction.text,
                "alignment_status": extraction.alignment_status,
                "confidence": extraction.confidence,
                "char_start": extraction.char_start,
                "char_end": extraction.char_end,
                "attributes": _attr_dict(extraction),
                "color": _color_for_entity(extraction.entity, index),
            }
        )
    return payload


def render_reviewer_html(document: DocumentResult, *, title: str = "Sourcery Reviewer") -> str:
    payload = _build_payload(document)
    entities = sorted({item["entity"] for item in payload})
    highlighted = _highlighted_text(document, payload) if payload else html.escape(document.text)
    payload_json = json.dumps(payload, ensure_ascii=False)
    entity_options = "".join(
        ["<option value=''>All entities</option>"]
        + [
            f"<option value='{html.escape(entity)}'>{html.escape(entity)}</option>"
            for entity in entities
        ]
    )

    return (
        "<style>"
        ":root{--bg:#f5f9ff;--line:#d8e2f2;--ink:#1b2a41;--muted:#54657f;--ok:#2f855a;--bad:#c53030;--warn:#b7791f;}"
        ".sr-root{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;color:var(--ink);background:var(--bg);padding:12px;}"
        ".sr-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:10px;}"
        ".sr-toolbar{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:8px;align-items:end;}"
        ".sr-field label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px;}"
        ".sr-field input,.sr-field select{width:100%;border:1px solid var(--line);border-radius:8px;padding:7px 8px;font-size:13px;background:#fff;}"
        ".sr-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;}"
        ".sr-btn{border:1px solid #bfd1ec;border-radius:8px;padding:6px 10px;background:#edf4ff;color:#21406f;font-size:12px;cursor:pointer;}"
        ".sr-btn:hover{background:#ddeaff;}"
        ".sr-btn-ok{background:#edfdf3;border-color:#b9edcb;color:var(--ok);}"
        ".sr-btn-bad{background:#fff2f2;border-color:#f2c3c3;color:var(--bad);}"
        ".sr-layout{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.2fr);gap:10px;}"
        ".sr-list{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:10px;}"
        ".sr-row{padding:8px 10px;border-bottom:1px solid #eef3fb;display:grid;grid-template-columns:1fr auto;gap:8px;cursor:pointer;}"
        ".sr-row:last-child{border-bottom:none;}"
        ".sr-row:hover{background:#f7fbff;}"
        ".sr-row-selected{background:#e9f2ff;}"
        ".sr-row-main{font-size:13px;line-height:1.3;}"
        ".sr-row-meta{font-size:11px;color:var(--muted);margin-top:2px;}"
        ".sr-pill{display:inline-block;padding:1px 6px;border-radius:999px;font-size:11px;border:1px solid #d5dfef;margin-left:6px;}"
        ".sr-pill-pending{background:#fff8e6;color:var(--warn);}"
        ".sr-pill-approved{background:#ebfbee;color:var(--ok);}"
        ".sr-pill-rejected{background:#fff1f1;color:var(--bad);}"
        ".sr-row-controls{display:flex;gap:6px;align-items:flex-start;}"
        ".sr-mini{border:1px solid #c9d8ef;background:#f7fbff;border-radius:6px;padding:3px 7px;font-size:11px;cursor:pointer;}"
        ".sr-mini-ok{border-color:#b9edcb;background:#edfdf3;color:var(--ok);}"
        ".sr-mini-bad{border-color:#f2c3c3;background:#fff2f2;color:var(--bad);}"
        ".sr-text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;"
        "line-height:1.5;max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:10px;background:#fff;}"
        ".sr-highlight{padding:1px;border-radius:4px;cursor:pointer;}"
        ".sr-highlight-selected{outline:2px solid #204978;}"
        ".sr-detail{font-size:12px;white-space:pre-wrap;background:#f7fbff;border:1px solid var(--line);border-radius:10px;padding:10px;margin-top:8px;}"
        ".sr-empty{font-size:13px;color:var(--muted);padding:12px;}"
        "@media (max-width: 980px){.sr-toolbar{grid-template-columns:1fr 1fr;}.sr-layout{grid-template-columns:1fr;}}"
        "</style>"
        "<div class='sr-root'>"
        f"<h2>{html.escape(title)}</h2>"
        "<div class='sr-card'>"
        "<div class='sr-toolbar'>"
        "<div class='sr-field'><label>Search</label><input id='sr-search' placeholder='Find text or attributes' /></div>"
        f"<div class='sr-field'><label>Entity</label><select id='sr-entity'>{entity_options}</select></div>"
        "<div class='sr-field'><label>Status</label><select id='sr-status'>"
        "<option value=''>All statuses</option>"
        "<option value='pending'>Pending</option>"
        "<option value='approved'>Approved</option>"
        "<option value='rejected'>Rejected</option>"
        "</select></div>"
        "<div class='sr-field'><label>Document</label>"
        f"<input id='sr-document' value='{html.escape(document.document_id)}' readonly /></div>"
        "</div>"
        "<div class='sr-actions'>"
        "<button class='sr-btn' id='sr-reset-filtered'>Reset Filtered</button>"
        "<button class='sr-btn sr-btn-ok' id='sr-approve-filtered'>Approve Filtered</button>"
        "<button class='sr-btn sr-btn-bad' id='sr-reject-filtered'>Reject Filtered</button>"
        "<button class='sr-btn' id='sr-export-jsonl'>Export Approved JSONL</button>"
        "<button class='sr-btn' id='sr-export-csv'>Export Approved CSV</button>"
        "</div>"
        "</div>"
        "<div class='sr-layout'>"
        "<div class='sr-card'><div id='sr-list' class='sr-list'></div></div>"
        "<div class='sr-card'>"
        f"<div id='sr-text' class='sr-text'>{highlighted}</div>"
        "<div id='sr-detail' class='sr-detail'></div>"
        "</div>"
        "</div>"
        "</div>"
        "<script>"
        f"const srPayload={payload_json};"
        f"const srDocId={json.dumps(document.document_id)};"
        "const srStorageKey='sourcery-review:'+srDocId;"
        "function srReadSaved(){try{return JSON.parse(localStorage.getItem(srStorageKey)||'{}');}catch(_){return {};}}"
        "function srSave(statusByIdx){localStorage.setItem(srStorageKey,JSON.stringify(statusByIdx));}"
        "const srSaved=srReadSaved();"
        "const srState=srPayload.map(item=>({...item,review_status:srSaved[item.idx]||'pending'}));"
        "let srSelected=srState.length?srState[0].idx:null;"
        "const srSearch=document.getElementById('sr-search');"
        "const srEntity=document.getElementById('sr-entity');"
        "const srStatus=document.getElementById('sr-status');"
        "const srList=document.getElementById('sr-list');"
        "const srDetail=document.getElementById('sr-detail');"
        "const srText=document.getElementById('sr-text');"
        "function srStatusClass(status){if(status==='approved')return 'sr-pill-approved';if(status==='rejected')return 'sr-pill-rejected';return 'sr-pill-pending';}"
        "function srFilter(item){"
        "const query=(srSearch.value||'').trim().toLowerCase();"
        "const entity=srEntity.value||'';"
        "const status=srStatus.value||'';"
        "if(entity&&item.entity!==entity)return false;"
        "if(status&&item.review_status!==status)return false;"
        "if(!query)return true;"
        "const hay=JSON.stringify({text:item.text,attributes:item.attributes,entity:item.entity}).toLowerCase();"
        "return hay.includes(query);"
        "}"
        "function srFiltered(){return srState.filter(srFilter);}"
        "function srStatusMap(){const out={};for(const item of srState){out[item.idx]=item.review_status;}return out;}"
        "function srSelect(idx){srSelected=idx;srRender();}"
        "function srSetStatus(idx,status){const item=srState.find(v=>v.idx===idx);if(!item)return;item.review_status=status;srSave(srStatusMap());srRender();}"
        "function srBulkSet(status){for(const item of srFiltered()){item.review_status=status;}srSave(srStatusMap());srRender();}"
        "function srRender(){"
        "const rows=srFiltered();"
        "if(!rows.length){srList.innerHTML=\"<div class='sr-empty'>No extractions match current filters.</div>\";}"
        "else{"
        "srList.innerHTML=rows.map(item=>`"
        "<div class='sr-row ${item.idx===srSelected?'sr-row-selected':''}' data-idx='${item.idx}'>"
        "<div class='sr-row-main'>${item.text}<span class='sr-pill ${srStatusClass(item.review_status)}'>${item.review_status}</span>"
        "<div class='sr-row-meta'>${item.entity} | ${item.char_start}-${item.char_end} | ${item.alignment_status}</div></div>"
        "<div class='sr-row-controls'>"
        "<button class='sr-mini sr-mini-ok' data-action='approve'>Approve</button>"
        "<button class='sr-mini sr-mini-bad' data-action='reject'>Reject</button>"
        "<button class='sr-mini' data-action='reset'>Reset</button>"
        "</div></div>`).join('');"
        "}"
        "for(const el of srList.querySelectorAll('.sr-row')){"
        "el.addEventListener('click',ev=>{"
        "const idx=Number(el.getAttribute('data-idx'));"
        "const target=ev.target;"
        "if(target&&target.getAttribute){"
        "const action=target.getAttribute('data-action');"
        "if(action==='approve'){srSetStatus(idx,'approved');ev.stopPropagation();return;}"
        "if(action==='reject'){srSetStatus(idx,'rejected');ev.stopPropagation();return;}"
        "if(action==='reset'){srSetStatus(idx,'pending');ev.stopPropagation();return;}"
        "}"
        "srSelect(idx);"
        "});"
        "}"
        "const selected=srState.find(item=>item.idx===srSelected) || null;"
        "srDetail.textContent=selected?JSON.stringify({"
        "entity:selected.entity,"
        "text:selected.text,"
        "status:selected.review_status,"
        "alignment:selected.alignment_status,"
        "confidence:selected.confidence,"
        "char_start:selected.char_start,"
        "char_end:selected.char_end,"
        "attributes:selected.attributes"
        "},null,2):'Select an extraction to inspect attributes.';"
        "for(const mark of srText.querySelectorAll('.sr-highlight')){"
        "const idx=Number(mark.getAttribute('data-idx'));"
        "mark.classList.toggle('sr-highlight-selected',idx===srSelected);"
        "mark.onclick=()=>srSelect(idx);"
        "}"
        "}"
        "function srDownload(filename,content,mime){"
        "const blob=new Blob([content],{type:mime});"
        "const url=URL.createObjectURL(blob);"
        "const a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);"
        "}"
        "function srApproved(){return srState.filter(item=>item.review_status==='approved');}"
        "function srExportJsonl(){"
        "const lines=srApproved().map(item=>JSON.stringify({"
        "entity:item.entity,text:item.text,alignment_status:item.alignment_status,confidence:item.confidence,"
        "char_start:item.char_start,char_end:item.char_end,attributes:item.attributes,review_status:item.review_status"
        "}));"
        "srDownload('sourcery-approved.jsonl',lines.join('\\n'),'application/x-ndjson');"
        "}"
        "function srCsvEscape(value){const s=String(value??'');if(s.includes(',')||s.includes('\"')||s.includes('\\n')){return '\"'+s.replaceAll('\"','\"\"')+'\"';}return s;}"
        "function srExportCsv(){"
        "const rows=srApproved();"
        "const header=['entity','text','alignment_status','confidence','char_start','char_end','attributes','review_status'];"
        "const body=rows.map(item=>[item.entity,item.text,item.alignment_status,item.confidence,item.char_start,item.char_end,JSON.stringify(item.attributes),item.review_status].map(srCsvEscape).join(','));"
        "srDownload('sourcery-approved.csv',[header.join(',')].concat(body).join('\\n'),'text/csv');"
        "}"
        "document.getElementById('sr-approve-filtered').onclick=()=>srBulkSet('approved');"
        "document.getElementById('sr-reject-filtered').onclick=()=>srBulkSet('rejected');"
        "document.getElementById('sr-reset-filtered').onclick=()=>srBulkSet('pending');"
        "document.getElementById('sr-export-jsonl').onclick=srExportJsonl;"
        "document.getElementById('sr-export-csv').onclick=srExportCsv;"
        "srSearch.addEventListener('input',srRender);"
        "srEntity.addEventListener('change',srRender);"
        "srStatus.addEventListener('change',srRender);"
        "srRender();"
        "</script>"
    )


def write_reviewer_html(
    data_source: DocumentResult | str | Path,
    output_path: str | Path,
    *,
    title: str = "Sourcery Reviewer",
) -> Path:
    if isinstance(data_source, (str, Path)):
        docs = load_document_results_jsonl(data_source)
        if not docs:
            raise ValueError(f"No documents found in: {data_source}")
        document = docs[0]
    else:
        document = data_source

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_document = (
        "<html><head><meta charset='utf-8'><title>"
        + html.escape(title)
        + "</title></head><body>"
        + render_reviewer_html(document, title=title)
        + "</body></html>"
    )
    output.write_text(html_document, encoding="utf-8")
    return output
