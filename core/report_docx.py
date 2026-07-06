#!/usr/bin/env python3
"""Minimal DOCX renderer for investigation print packages."""
from __future__ import annotations

import base64
import binascii
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


def render_print_package_docx(packet: dict[str, Any]) -> bytes:
    """Render a Word-openable DOCX from an investigation packet.

    This intentionally avoids heavyweight runtime dependencies. The renderer
    consumes the same print_package manifest exposed through report_exports and
    preserves the full Markdown report body as document text.
    """
    report_exports = _dict(packet.get("report_exports"))
    print_package = _dict(report_exports.get("print_package"))
    report_markdown = str(packet.get("report_markdown") or "")
    company = str(packet.get("summary", {}).get("company") or packet.get("input") or "Subject")
    image_assets = _embedded_image_assets(_dict(print_package.get("image_evidence_inventory")))
    paragraphs = _document_paragraphs(company, report_markdown, print_package, image_assets)
    document_xml = _document_xml(paragraphs)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", _content_types_xml())
        docx.writestr("_rels/.rels", _rels_xml())
        docx.writestr("word/_rels/document.xml.rels", _document_rels_xml(image_assets))
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/footer1.xml", _footer_xml())
        docx.writestr("word/styles.xml", _styles_xml())
        docx.writestr("docProps/core.xml", _core_props_xml(company))
        docx.writestr("docProps/app.xml", _app_props_xml())
        for asset in image_assets:
            docx.writestr(f"word/media/{asset['filename']}", asset["bytes"])
    return buffer.getvalue()


def _document_paragraphs(
    company: str,
    report_markdown: str,
    print_package: dict[str, Any],
    image_assets: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    front = _dict(print_package.get("red_head_front_matter"))
    layout = _dict(print_package.get("print_layout"))
    checklist = [str(item) for item in print_package.get("acceptance_checklist", []) if str(item).strip()]
    charts = [_dict(item) for item in print_package.get("chart_manifest", []) if isinstance(item, dict)]
    image_inventory = _dict(print_package.get("image_evidence_inventory"))
    source_appendix = _dict(print_package.get("source_provenance_appendix"))
    relationship_capital_appendix = _dict(print_package.get("relationship_capital_appendix"))
    delivery_checklist = _dict(print_package.get("delivery_checklist"))
    image_assets_by_id = {
        str(asset.get("inventory_id")): asset
        for asset in image_assets or []
        if str(asset.get("inventory_id") or "").strip()
    }
    operational_handoff = _dict(print_package.get("operational_handoff"))
    sections = [_dict(item) for item in print_package.get("section_inventory", []) if isinstance(item, dict)]
    document_number = str(front.get("document_number") or "WST-DD-UNNUMBERED").strip()
    issuing_body = str(front.get("issuing_body") or "Wallstreet Tieling Enterprise Intelligence Desk").strip()
    paragraphs: list[dict[str, Any]] = [
        {"text": issuing_body, "style": "RedHead"},
        {"raw_xml": _red_head_rule_xml()},
        {"text": str(front.get("document_title") or f"{company} Due Diligence Result Brief"), "style": "Title"},
        {"raw_xml": _official_metadata_table_xml(company, front)},
        {"text": f"Document class: {front.get('classification') or 'internal_reference'}", "style": "Meta"},
        {"text": f"Document number: {document_number}", "style": "Meta"},
        {"text": "Concise Due-Diligence Brief", "style": "Heading1"},
        {
            "text": (
                "This front section summarizes the generated due-diligence packet. "
                "The full investigation body follows without reducing the source report text."
            ),
            "style": "Normal",
        },
        {"text": "Table Of Contents", "style": "Heading1"},
    ]
    if sections:
        for section in sections[:40]:
            paragraphs.append(
                {
                    "text": (
                        f"L{section.get('heading_level') or 1} "
                        f"{section.get('title') or 'Untitled section'} | "
                        f"role={section.get('print_role') or 'body'} | "
                        f"line={section.get('line_start') or 0}"
                    ),
                    "style": "TOC",
                }
            )
    else:
        paragraphs.append({"text": "No report section inventory was available.", "style": "Normal"})
    paragraphs.extend([
        {"text": "Print Layout Contract", "style": "Heading2"},
        {
            "text": (
                f"Paper={layout.get('paper') or 'A4'}; "
                f"binding_margin={layout.get('binding_margin') or 'wide_inner_margin'}; "
                f"page_numbers={bool(layout.get('page_numbers'))}; "
                f"table_of_contents={bool(layout.get('table_of_contents'))}."
            ),
            "style": "Normal",
        },
    ])
    paragraphs.extend(_delivery_checklist_paragraphs(delivery_checklist))
    paragraphs.extend(_operational_handoff_paragraphs(operational_handoff))
    paragraphs.append({"text": "Risk And Capital Chart Plan", "style": "Heading1"})
    if charts:
        for chart in charts:
            paragraphs.append(
                {
                    "text": f"{chart.get('id')}: {chart.get('title')} | {chart.get('type')}",
                    "style": "Bullet",
                }
            )
            chart_rows = _chart_table_rows(chart)
            if chart_rows:
                paragraphs.append({"raw_xml": _table_xml(["Metric", "Value"], chart_rows)})
            visual_rows = _chart_visual_rows(chart)
            if visual_rows:
                paragraphs.append({"text": "Chart Visual Summary", "style": "Heading2"})
                paragraphs.append({"raw_xml": _table_xml(["Metric", "Value", "Share", "Bar"], visual_rows)})
            for row in _chart_data_rows(chart):
                paragraphs.append({"text": row, "style": "DataRow"})
    else:
        paragraphs.append({"text": "No chart manifest was available.", "style": "Normal"})
    image_items = [_dict(item) for item in image_inventory.get("items", []) if isinstance(item, dict)]
    paragraphs.extend(
        [
            {"text": "Image Evidence Appendix", "style": "Heading1"},
            {
                "text": (
                    f"Image evidence count: {image_inventory.get('count') or 0}. "
                    f"{image_inventory.get('empty_state') or 'See packet image evidence inventory.'}"
                ),
                "style": "Normal",
            },
        ]
    )
    if image_items:
        table_rows: list[list[str]] = []
        for image in image_items[:40]:
            table_rows.append(
                [
                    str(image.get("id") or ""),
                    str(image.get("caption") or "Evidence image"),
                    str(image.get("source") or "unknown"),
                    str(image.get("admission") or "unknown"),
                    str(image.get("url") or ""),
                ]
            )
            paragraphs.append(
                {
                    "text": (
                        f"{image.get('id')}: {image.get('caption') or 'Evidence image'} | "
                        f"source={image.get('source') or 'unknown'} | "
                        f"admission={image.get('admission') or 'unknown'}"
                    ),
                    "style": "Bullet",
                }
            )
            if image.get("url"):
                paragraphs.append({"text": f"url={image.get('url')}", "style": "DataRow"})
            asset = image_assets_by_id.get(str(image.get("id") or ""))
            if asset:
                paragraphs.append(
                    {
                        "raw_xml": _image_paragraph_xml(
                            str(asset["relationship_id"]),
                            str(image.get("caption") or "Evidence image"),
                        )
                    }
                )
                paragraphs.append({"text": "embedded_image_status=embedded_in_docx", "style": "DataRow"})
        if table_rows:
            paragraphs.append({"raw_xml": _table_xml(["ID", "Caption", "Source", "Admission", "URL"], table_rows)})
    paragraphs.extend(_source_provenance_paragraphs(source_appendix))
    paragraphs.extend(_relationship_capital_paragraphs(relationship_capital_appendix))
    paragraphs.append({"text": "Full Due-Diligence Body", "style": "Heading1"})
    paragraphs.extend(_markdown_to_paragraphs(report_markdown))
    paragraphs.append({"text": "Renderer Acceptance Checklist", "style": "Heading1"})
    for item in checklist:
        paragraphs.append({"text": item, "style": "Bullet"})
    return paragraphs


def _source_provenance_paragraphs(source_appendix: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = [{"text": "Source Provenance Appendix", "style": "Heading1"}]
    if not source_appendix:
        paragraphs.append({"text": "No source provenance appendix was available.", "style": "Normal"})
        return paragraphs

    policy = str(source_appendix.get("policy") or "").strip()
    if policy:
        paragraphs.append({"text": f"Policy: {policy}", "style": "Normal"})
    paragraphs.append(
        {
            "text": (
                f"sources={source_appendix.get('source_count') or 0}; "
                f"evidence_rows={source_appendix.get('evidence_row_count') or 0}; "
                f"truncated={bool(source_appendix.get('truncated'))}"
            ),
            "style": "DataRow",
        }
    )

    source_counts = _dict(source_appendix.get("source_counts"))
    authority_counts = _dict(source_appendix.get("authority_counts"))
    admission_counts = _dict(source_appendix.get("admission_counts"))
    summary_rows: list[list[str]] = []
    for key, value in sorted(source_counts.items())[:12]:
        summary_rows.append(["source", _cell_text(key), _cell_text(value)])
    for key, value in sorted(authority_counts.items())[:12]:
        summary_rows.append(["authority", _cell_text(key), _cell_text(value)])
    for key, value in sorted(admission_counts.items())[:12]:
        summary_rows.append(["admission", _cell_text(key), _cell_text(value)])
    if summary_rows:
        paragraphs.append({"text": "Source Provenance Summary", "style": "Heading2"})
        paragraphs.append({"raw_xml": _table_xml(["Group", "Value", "Count"], summary_rows)})

    rows = [_dict(item) for item in source_appendix.get("rows", []) if isinstance(item, dict)]
    if rows:
        paragraphs.append({"text": "Evidence Source Index", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["ID", "Source", "Authority", "Access", "Admission", "Confidence", "URL"],
                    [
                        [
                            _cell_text(row.get("id")),
                            _cell_text(row.get("source")),
                            _cell_text(row.get("authority")),
                            _cell_text(row.get("access")),
                            _cell_text(row.get("admission")),
                            _cell_text(row.get("confidence")),
                            _cell_text(row.get("url"), 220),
                        ]
                        for row in rows[:40]
                    ],
                )
            }
        )
    else:
        paragraphs.append(
            {
                "text": source_appendix.get("empty_state") or "No evidence rows were available for source provenance review.",
                "style": "Normal",
            }
        )
    return paragraphs


def _relationship_capital_paragraphs(appendix: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = [{"text": "Relationship And Capital Appendix", "style": "Heading1"}]
    if not appendix:
        paragraphs.append({"text": "No relationship or capital appendix was available.", "style": "Normal"})
        return paragraphs

    policy = str(appendix.get("policy") or "").strip()
    if policy:
        paragraphs.append({"text": f"Policy: {policy}", "style": "Normal"})
    paragraphs.append(
        {
            "text": (
                f"capital_relationship_status={appendix.get('capital_relationship_status') or 'unknown'}; "
                f"relationship_edges={appendix.get('relationship_edge_count') or 0}; "
                f"evidence_backed_edges={appendix.get('relationship_evidence_backed_edge_count') or 0}; "
                f"lead_only_edges={appendix.get('relationship_lead_only_edge_count') or 0}; "
                f"missing_evidence_edges={appendix.get('relationship_missing_evidence_edge_count') or 0}; "
                f"capital_verification_steps={appendix.get('capital_verification_queue_count') or 0}; "
                f"relationship_audit_steps={appendix.get('relationship_audit_queue_count') or 0}"
            ),
            "style": "DataRow",
        }
    )

    graph_summary = _dict(appendix.get("graph_capital_exposure_summary"))
    if graph_summary:
        paragraphs.append({"text": "Graph Capital Exposure Summary", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["Field", "Value"],
                    [[str(key), _cell_text(graph_summary[key], 220)] for key in sorted(graph_summary)],
                )
            }
        )

    capital_queue = [_dict(item) for item in appendix.get("capital_verification_queue", []) if isinstance(item, dict)]
    if capital_queue:
        paragraphs.append({"text": "Capital Verification Queue", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["Step", "Priority", "Kind", "Target", "Source", "Done Condition"],
                    [
                        [
                            _cell_text(row.get("step_id")),
                            _cell_text(row.get("priority")),
                            _cell_text(row.get("kind")),
                            _cell_text(row.get("target_title") or row.get("target_id")),
                            _cell_text(row.get("source")),
                            _cell_text(row.get("done_condition"), 260),
                        ]
                        for row in capital_queue[:20]
                    ],
                )
            }
        )

    relationship_queue = [_dict(item) for item in appendix.get("relationship_audit_queue", []) if isinstance(item, dict)]
    if relationship_queue:
        paragraphs.append({"text": "Relationship Graph Audit Queue", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["Step", "Priority", "Kind", "Subject", "Relation", "Done Condition"],
                    [
                        [
                            _cell_text(row.get("step_id")),
                            _cell_text(row.get("priority")),
                            _cell_text(row.get("kind")),
                            _cell_text(row.get("subject") or row.get("from") or row.get("source")),
                            _cell_text(row.get("relation") or row.get("edge_type")),
                            _cell_text(row.get("done_condition"), 260),
                        ]
                        for row in relationship_queue[:20]
                    ],
                )
            }
        )

    if not capital_queue and not relationship_queue:
        paragraphs.append(
            {
                "text": appendix.get("empty_state") or "No capital verification or relationship graph audit rows were available.",
                "style": "Normal",
            }
        )
    return paragraphs


def _delivery_checklist_paragraphs(delivery_checklist: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = [{"text": "Delivery Checklist", "style": "Heading1"}]
    if not delivery_checklist:
        paragraphs.append({"text": "No delivery checklist manifest was available.", "style": "Normal"})
        return paragraphs

    policy = str(delivery_checklist.get("policy") or "").strip()
    if policy:
        paragraphs.append({"text": f"Policy: {policy}", "style": "Normal"})
    paragraphs.append(
        {
            "text": (
                f"status={delivery_checklist.get('status') or 'unknown'}; "
                f"primary_print_file={delivery_checklist.get('primary_print_file') or ''}; "
                f"primary_screen_file={delivery_checklist.get('primary_screen_file') or ''}"
            ),
            "style": "DataRow",
        }
    )

    output_rows = [_dict(item) for item in delivery_checklist.get("required_outputs", []) if isinstance(item, dict)]
    if output_rows:
        paragraphs.append({"text": "Required Delivery Outputs", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["Open", "ID", "File", "Role", "Required", "Produced By"],
                    [
                        [
                            _cell_text(row.get("open_order")),
                            _cell_text(row.get("id")),
                            _cell_text(row.get("filename")),
                            _cell_text(row.get("role")),
                            _cell_text(row.get("required")),
                            _cell_text(row.get("produced_by"), 220),
                        ]
                        for row in output_rows[:20]
                    ],
                )
            }
        )

    quality_rows = [_dict(item) for item in delivery_checklist.get("quality_checks", []) if isinstance(item, dict)]
    if quality_rows:
        paragraphs.append({"text": "Delivery Quality Checks", "style": "Heading2"})
        paragraphs.append(
            {
                "raw_xml": _table_xml(
                    ["ID", "Status", "Packet Ref", "Done Condition"],
                    [
                        [
                            _cell_text(row.get("id")),
                            _cell_text(row.get("status")),
                            _cell_text(row.get("packet_ref")),
                            _cell_text(row.get("done_condition"), 260),
                        ]
                        for row in quality_rows[:20]
                    ],
                )
            }
        )
    return paragraphs


def _operational_handoff_paragraphs(operational_handoff: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = [{"text": "Operational Handoff Appendix", "style": "Heading1"}]
    if not operational_handoff:
        paragraphs.append({"text": "No operational handoff manifest was available.", "style": "Normal"})
        return paragraphs

    policy = str(operational_handoff.get("policy") or "").strip()
    if policy:
        paragraphs.append({"text": f"Policy: {policy}", "style": "Normal"})

    summary = _dict(operational_handoff.get("summary"))
    if summary:
        rows = [[str(key), _cell_text(summary[key])] for key in sorted(summary)]
        paragraphs.append({"raw_xml": _table_xml(["Field", "Value"], rows)})

    cards = [_dict(item) for item in operational_handoff.get("cards", []) if isinstance(item, dict)]
    if not cards:
        paragraphs.append({"text": "No active operational follow-up cards were generated.", "style": "Normal"})
        return paragraphs

    card_rows: list[list[str]] = []
    for card in cards[:20]:
        card_rows.append(
            [
                _cell_text(card.get("id")),
                _cell_text(card.get("priority")),
                _cell_text(card.get("status")),
                _cell_text(card.get("source")),
                _cell_text(card.get("domain")),
                _cell_text(card.get("action"), 280),
                _cell_text(card.get("done_condition"), 220),
            ]
        )
        paragraphs.append(
            {
                "text": (
                    f"{card.get('id')}: {card.get('title') or 'Operational task'} | "
                    f"priority={card.get('priority') or '-'} | status={card.get('status') or '-'}"
                ),
                "style": "Bullet",
            }
        )
        hint = str(card.get("execution_hint") or "").strip()
        if hint:
            paragraphs.append({"text": f"execution_hint={hint}", "style": "DataRow"})
        admission_gate = str(card.get("admission_gate") or "").strip()
        if admission_gate:
            paragraphs.append({"text": f"admission_gate={admission_gate}", "style": "DataRow"})
        blocked_reason = str(card.get("blocked_reason") or "").strip()
        if blocked_reason:
            paragraphs.append({"text": f"blocked_reason={blocked_reason}", "style": "DataRow"})

    paragraphs.append(
        {
            "raw_xml": _table_xml(
                ["ID", "Priority", "Status", "Source", "Domain", "Action", "Done Condition"],
                card_rows,
            )
        }
    )
    return paragraphs


def _markdown_to_paragraphs(markdown: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            paragraphs.append({"text": heading.group(2).strip(), "style": f"Heading{min(level, 2)}"})
            continue
        if line.startswith(("- ", "* ")):
            paragraphs.append({"text": line[2:].strip(), "style": "Bullet"})
            continue
        paragraphs.append({"text": line, "style": "Normal"})
    return paragraphs


def _document_xml(paragraphs: list[dict[str, Any]]) -> str:
    body = "\n".join(
        str(item["raw_xml"]) if "raw_xml" in item else _paragraph_xml(item["text"], item.get("style", "Normal"))
        for item in paragraphs
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<w:body>{body}"
        '<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter1"/>'
        '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1200" w:bottom="1440" w:left="1700" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )


def _embedded_image_assets(image_inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Embed already-collected local/data-uri image evidence without fetching remote URLs."""
    assets: list[dict[str, Any]] = []
    items = [_dict(item) for item in image_inventory.get("items", []) if isinstance(item, dict)]
    for item in items[:20]:
        image_bytes, extension = _image_bytes_from_inventory_item(item)
        if not image_bytes:
            continue
        index = len(assets) + 1
        safe_extension = extension if extension in {"png", "jpg", "jpeg", "gif"} else "png"
        assets.append(
            {
                "inventory_id": str(item.get("id") or f"image-evidence-{index}"),
                "relationship_id": f"rIdImage{index}",
                "filename": f"evidence-image-{index}.{safe_extension}",
                "bytes": image_bytes,
                "extension": safe_extension,
            }
        )
    return assets


def _image_bytes_from_inventory_item(item: dict[str, Any]) -> tuple[bytes | None, str]:
    for key in ("image_base64", "base64", "data_base64"):
        raw = str(item.get(key) or "").strip()
        if raw:
            return _decode_base64_image(raw), str(item.get("extension") or "png").lower().strip(".")

    raw_url = str(item.get("url") or item.get("image_url") or "").strip()
    data_uri = re.match(r"^data:image/([a-zA-Z0-9+.-]+);base64,(.+)$", raw_url, flags=re.DOTALL)
    if data_uri:
        extension = data_uri.group(1).lower().replace("jpeg", "jpg")
        return _decode_base64_image(data_uri.group(2)), extension

    for key in ("local_path", "path", "file_path"):
        raw_path = str(item.get(key) or "").strip()
        if not raw_path:
            continue
        image_path = Path(raw_path)
        if not image_path.exists() or not image_path.is_file():
            continue
        extension = image_path.suffix.lower().strip(".")
        if extension not in {"png", "jpg", "jpeg", "gif"}:
            continue
        try:
            return image_path.read_bytes(), extension
        except OSError:
            return None, extension
    return None, "png"


def _decode_base64_image(raw: str) -> bytes | None:
    try:
        return base64.b64decode(str(raw).strip(), validate=True)
    except (binascii.Error, ValueError):
        return None


def _image_paragraph_xml(relationship_id: str, caption: str) -> str:
    cx = 4572000
    cy = 2743200
    descr = escape(caption or "Evidence image")
    rid = escape(relationship_id)
    return (
        "<w:p><w:r><w:drawing>"
        "<wp:inline distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\">"
        f"<wp:extent cx=\"{cx}\" cy=\"{cy}\"/>"
        f"<wp:docPr id=\"1\" name=\"Evidence image\" descr=\"{descr}\"/>"
        "<a:graphic><a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:pic>"
        "<pic:nvPicPr><pic:cNvPr id=\"0\" name=\"Evidence image\"/><pic:cNvPicPr/></pic:nvPicPr>"
        "<pic:blipFill>"
        f"<a:blip r:embed=\"{rid}\"/>"
        "<a:stretch><a:fillRect/></a:stretch>"
        "</pic:blipFill>"
        "<pic:spPr>"
        f"<a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"{cx}\" cy=\"{cy}\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom>"
        "</pic:spPr>"
        "</pic:pic>"
        "</a:graphicData></a:graphic>"
        "</wp:inline>"
        "</w:drawing></w:r></w:p>"
    )


def _paragraph_xml(text: str, style: str) -> str:
    style_id = {
        "Title": "Title",
        "RedHead": "RedHead",
        "Meta": "Meta",
        "Heading1": "Heading1",
        "Heading2": "Heading2",
        "Bullet": "Bullet",
        "TOC": "TOC",
        "DataRow": "DataRow",
    }.get(style, "Normal")
    return (
        "<w:p>"
        f'<w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>'
        f"<w:r><w:t xml:space=\"preserve\">{escape(str(text))}</w:t></w:r>"
        "</w:p>"
    )


def _compact_data(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{key}={value[key]}" for key in sorted(value)[:8])
    return str(value or "")


def _cell_text(value: Any, limit: int = 180) -> str:
    text = _compact_data(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _chart_data_rows(chart: dict[str, Any]) -> list[str]:
    data = chart.get("data")
    if isinstance(data, dict):
        return [f"data.{key}={data[key]}" for key in sorted(data)[:12]]
    if isinstance(data, list):
        rows: list[str] = []
        for index, item in enumerate(data[:12], start=1):
            if isinstance(item, dict):
                rows.append(
                    f"data[{index}]="
                    + "; ".join(f"{key}={item[key]}" for key in sorted(item)[:8])
                )
            else:
                rows.append(f"data[{index}]={item}")
        return rows
    compact = _compact_data(data)
    return [f"data={compact}"] if compact else []


def _chart_table_rows(chart: dict[str, Any]) -> list[list[str]]:
    data = chart.get("data")
    if isinstance(data, dict):
        return [[str(key), str(data[key])] for key in sorted(data)[:12]]
    if isinstance(data, list):
        rows: list[list[str]] = []
        for index, item in enumerate(data[:12], start=1):
            if isinstance(item, dict):
                rows.append(
                    [
                        str(index),
                        "; ".join(f"{key}={item[key]}" for key in sorted(item)[:8]),
                    ]
                )
            else:
                rows.append([str(index), str(item)])
        return rows
    compact = _compact_data(data)
    return [["data", compact]] if compact else []


def _chart_visual_rows(chart: dict[str, Any]) -> list[list[str]]:
    data = chart.get("data")
    if not isinstance(data, dict):
        return []

    numeric_items: list[tuple[str, float]] = []
    for key in sorted(data):
        value = data[key]
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number < 0:
            continue
        numeric_items.append((str(key), number))

    total = sum(number for _, number in numeric_items)
    if total <= 0:
        return []

    rows: list[list[str]] = []
    for key, number in numeric_items[:12]:
        share = number / total
        bar_width = max(1, round(share * 20)) if number > 0 else 0
        rows.append(
            [
                key,
                _format_number(number),
                f"{share:.0%}",
                "#" * bar_width,
            ]
        )
    return rows


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _official_metadata_table_xml(company: str, front: dict[str, Any]) -> str:
    rows = [
        ["Subject", company],
        ["Document No.", str(front.get("document_number") or "WST-DD-UNNUMBERED")],
        ["Issuing Body", str(front.get("issuing_body") or "Wallstreet Tieling Enterprise Intelligence Desk")],
        ["Classification", str(front.get("classification") or "internal_reference")],
        ["Purpose", str(front.get("document_purpose") or "desktop_agent_due_diligence_delivery")],
    ]
    return _table_xml(["Field", "Value"], rows)


def _red_head_rule_xml() -> str:
    return (
        "<w:p>"
        "<w:pPr><w:pBdr>"
        '<w:bottom w:val="single" w:sz="18" w:space="2" w:color="9F1D20"/>'
        "</w:pBdr></w:pPr>"
        "<w:r><w:t> </w:t></w:r>"
        "</w:p>"
    )


def _table_xml(headers: list[str], rows: list[list[str]]) -> str:
    all_rows = [headers, *rows]
    body = "".join(_table_row_xml(row, header=index == 0) for index, row in enumerate(all_rows))
    return (
        "<w:tbl>"
        "<w:tblPr><w:tblStyle w:val=\"TableGrid\"/>"
        "<w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "<w:tblBorders>"
        "<w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "<w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "<w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>"
        "</w:tblBorders></w:tblPr>"
        f"{body}"
        "</w:tbl>"
    )


def _table_row_xml(cells: list[str], *, header: bool = False) -> str:
    return "<w:tr>" + "".join(_table_cell_xml(cell, header=header) for cell in cells) + "</w:tr>"


def _table_cell_xml(text: str, *, header: bool = False) -> str:
    shading = '<w:shd w:fill="F2F2F2"/>' if header else ""
    run_props = "<w:b/>" if header else ""
    return (
        "<w:tc>"
        f"<w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/>{shading}</w:tcPr>"
        "<w:p><w:r>"
        f"<w:rPr>{run_props}</w:rPr>"
        f"<w:t xml:space=\"preserve\">{escape(str(text))}</w:t>"
        "</w:r></w:p>"
        "</w:tc>"
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpg" ContentType="image/jpeg"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Default Extension="gif" ContentType="image/gif"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _document_rels_xml(image_assets: list[dict[str, Any]] | None = None) -> str:
    image_relationships = "".join(
        (
            f'<Relationship Id="{escape(str(asset["relationship_id"]))}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="media/{escape(str(asset["filename"]))}"/>'
        )
        for asset in image_assets or []
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdFooter1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        f"{image_relationships}"
        "</Relationships>"
    )


def _footer_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
        '<w:r><w:t>Page </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>1</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p></w:ftr>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="RedHead"><w:name w:val="RedHead"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:color w:val="9F1D20"/><w:sz w:val="30"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Meta"><w:name w:val="Meta"/><w:rPr><w:color w:val="666666"/><w:sz w:val="20"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Bullet"><w:name w:val="Bullet"/><w:pPr><w:ind w:left="720"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="TOC"><w:name w:val="TOC"/><w:pPr><w:ind w:left="360"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="DataRow"><w:name w:val="DataRow"/><w:pPr><w:ind w:left="1080"/></w:pPr><w:rPr><w:sz w:val="18"/><w:color w:val="555555"/></w:rPr></w:style>'
        "</w:styles>"
    )


def _core_props_xml(company: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{escape(company)} due diligence report</dc:title>"
        "<dc:creator>Wallstreet Tieling</dc:creator>"
        "</cp:coreProperties>"
    )


def _app_props_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Wallstreet Tieling</Application>"
        "</Properties>"
    )
