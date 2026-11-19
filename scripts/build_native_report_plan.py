#!/usr/bin/env python3
"""Build an offline native-Google-Docs authoring plan; never call Google APIs.

The author copies the v0 Google Doc natively and preserves its 22 equation
paragraphs. This script parses report/report.md into native blocks and the 23
text segments around those equations. All write indexes must come from fresh
connector readback, not from this file or archived evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path


EXPECTED_EQUATIONS = [
    r"A_s(b,r)=b^2-(4-\pi)r^2,\quad c=b/2-r",
    r"I_s(b,r)=\frac{b^4}{12}-4[c^2r^2(1-\pi/4)+cr^3/3+r^4(1/3-\pi/16)]",
    r"A=A_s(b,r_o)-A_s(b-2t,r_i),\quad I=I_s(b,r_o)-I_s(b-2t,r_i)",
    r"W=A_{max}L\rho g\,10^{-9},\quad q=W/L",
    r"M_{max}=FL/4+qL^2/8",
    r"M_e=Fc_{max}\sqrt2,\quad\sigma_b=\sqrt2(M_{max}+M_e)/Z,\quad\sigma_a=F/A_{min}",
    r"T=Fc_{max}\sqrt2,\quad\tau_T=T/(2A_m t_{min}),\quad\tau_V=1.5(F+W)/[2t_{min}(b_{min}-2t_{min})]",
    r"\sigma_{vm}=\sqrt{(\sigma_b+\sigma_a)^2+3(\tau_T+\tau_V)^2}",
    r"\delta=FL^3/(48EI)+5qL^4/(384EI)+M_eL^2/(8EI)",
    r"P_E=\pi^2EI/L^2,\quad P_{allow}=\min(P_E,\sigma_yA_{min})/3",
    r"A_p=B^2-2C^2",
    r"I_p=B^4/12-4[(C^2/2)(B/2-C/3)^2+C^4/36],\quad Z_p=I_p/(B/2)",
    r"\sigma_p=\sqrt2(R\ell+M_t)/Z_p+R/A_p,\quad\tau_p=1.5R/a^2+T/(0.208a^3)",
    r"\sigma_{p,vm}=\sqrt{\sigma_p^2+3\tau_p^2},\quad\delta_p=R\ell^3/(3E_pI_p)+M_t\ell^2/(2E_pI_p)",
    r"\sigma_{plate}=(Rs/4)/(wt_p^2/6),\quad F_c=R+M_t/(\ell_{eng}-10)",
    r"p_{bearing}=F_c/[(B-2C)10],\quad\sigma_{wall}=[F_c(b_{max}-2t_{min})/4]/(10t_{min}^2/6)",
    r"t_{fix,max}=(8+0.1)+(1.5+0.3)=9.9\;\mathrm{mm}\le10\;\mathrm{mm}",
    r"N=R+(Re+M_t)/s,\quad V=R+T/s",
    r"M_b=V(t_{fix,max}+0.5d)+Re+M_t",
    r"U=N/700+V/4300+M_b/6285.714\le1",
    r"F_{pre}=T_{inst}/(Kd),\quad A_{s,min}=\pi(17.6^2-6.5^2)/4",
    r"S_{bound}=\sqrt{S_{fx}^2+S_{fy}^2+S_{fz}^2}+S_{tx}+\sqrt{S_{my}^2+S_{mz}^2}",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def inline(text: str, sources: dict[str, str] | None = None) -> dict:
    """Parse the report's inline Markdown without changing visible wording.

    Returned style offsets are UTF-16 units relative to this block's text.
    Unsupported Markdown is retained literally rather than silently dropped.
    """
    sources = sources or {}
    out: list[str] = []
    spans: list[dict] = []
    size = 0

    def emit(value: str, style: dict) -> None:
        nonlocal size
        start = size
        out.append(value)
        size += utf16(value)
        if value and style:
            if spans and spans[-1]["end_utf16"] == start and spans[-1]["style"] == style:
                spans[-1]["end_utf16"] = size
            else:
                spans.append({"start_utf16": start, "end_utf16": size, "style": dict(style)})

    def walk(value: str, style: dict) -> None:
        i = 0
        while i < len(value):
            if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in r"\`*{}[]()#+-.!|":
                emit(value[i + 1], style)
                i += 2
                continue
            if value[i] == "`":
                n = len(value[i:]) - len(value[i:].lstrip("`"))
                stop = value.find("`" * n, i + n)
                if stop >= 0:
                    emit(value[i + n:stop], {**style, "code": True})
                    i = stop + n
                    continue
            if value.startswith("**", i):
                stop = value.find("**", i + 2)
                if stop >= 0:
                    walk(value[i + 2:stop], {**style, "bold": True})
                    i = stop + 2
                    continue
            if value[i] == "*":
                stop = value.find("*", i + 1)
                if stop > i + 1:
                    walk(value[i + 1:stop], {**style, "italic": True})
                    i = stop + 1
                    continue
            if value[i] == "[":
                close = value.find("]", i + 1)
                if close >= 0 and value.startswith("](", close):
                    depth = 1
                    end = close + 2
                    while end < len(value) and depth:
                        if value[end] == "(": depth += 1
                        elif value[end] == ")": depth -= 1
                        end += 1
                    if depth == 0:
                        url = value[close + 2:end - 1]
                        if url.startswith(("https://", "http://", "mailto:")):
                            walk(value[i + 1:close], {**style, "link_url": url})
                            i = end
                            continue
                citation = re.match(r"\[(S\d+(?:\s+S\d+)*)\]", value[i:])
                if citation:
                    emit("[", style)
                    for part in re.split(r"(\s+)", citation.group(1)):
                        emit(part, {**style, **({"link_url": sources[part]} if part in sources else {})})
                    emit("]", style)
                    i += len(citation.group(0))
                    continue
            emit(value[i], style)
            i += 1

    walk(text, {})
    return {"text": "".join(out), "text_utf16_length": size, "runs": spans}


def split_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"): value = value[1:]
    if value.endswith("|"): value = value[:-1]
    cells: list[str] = []
    buffer: list[str] = []
    in_code = False
    escaped = False
    for char in value:
        if escaped:
            buffer.extend(["\\", char])
            escaped = False
        elif char == "\\": escaped = True
        elif char == "`":
            in_code = not in_code
            buffer.append(char)
        elif char == "|" and not in_code:
            cells.append("".join(buffer).strip())
            buffer = []
        else: buffer.append(char)
    if escaped: buffer.append("\\")
    cells.append("".join(buffer).strip())
    return cells


def table_separator(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        head = stream.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("Expected a PNG figure: " + str(path))
    return struct.unpack(">II", head[16:24])


def parse_markdown(markdown: str, root: Path, markdown_path: Path) -> list[dict]:
    sources = {m.group(1): m.group(2) for m in re.finditer(r"\[(S\d+)\s+[^\]]+\]\((https?://[^\s)]+)\)", markdown)}
    lines = markdown.splitlines()
    blocks: list[dict] = []
    n = 0
    equation = 0
    table = 0
    figure = 0

    def add(kind: str, first: int, last: int, **data) -> None:
        blocks.append({"type": kind, "source_lines": [first + 1, last + 1], **data})

    def special(k: int) -> bool:
        line = lines[k]
        return bool(not line.strip() or re.match(r"^(#{1,6})\s|^```|^\$\$\s*$|^!\[|^[-*]\s|^\d+[.)]\s", line) or (k + 1 < len(lines) and table_separator(lines[k + 1])))

    while n < len(lines):
        line = lines[n]
        if not line.strip():
            n += 1
            continue
        if line.strip() == "$$":
            end = n + 1
            while end < len(lines) and lines[end].strip() != "$$": end += 1
            if end == len(lines): raise ValueError(f"Unclosed equation at line {n + 1}")
            equation += 1
            latex = "\n".join(lines[n + 1:end]).strip()
            if equation > len(EXPECTED_EQUATIONS) or re.sub(r"\s+", "", latex) != re.sub(r"\s+", "", EXPECTED_EQUATIONS[equation - 1]):
                raise ValueError(f"Equation {equation} differs from the retained v0 ordinal contract; verify the native math before adapting the template")
            add("native_equation", n, end, ordinal=equation, latex_reference=latex,
                policy="retain_existing_native_equation_paragraph", insert_latex_as_text=False)
            n = end + 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            add("heading", n, n, markdown_level=level,
                named_style="TITLE" if level == 1 else "HEADING_" + str(level - 1),
                **inline(heading.group(2), sources))
            n += 1
            continue
        if line.startswith("```"):
            end = n + 1
            while end < len(lines) and not lines[end].startswith("```"): end += 1
            if end == len(lines): raise ValueError(f"Unclosed code fence at line {n + 1}")
            for k in range(n + 1, end):
                add("code_paragraph", k, k, language=line[3:].strip(), text=lines[k],
                    text_utf16_length=utf16(lines[k]), runs=[{"start_utf16": 0, "end_utf16": utf16(lines[k]), "style": {"code": True}}] if lines[k] else [])
            n = end + 1
            continue
        image = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line.strip())
        if image:
            figure += 1
            alt = inline(image.group(1), sources)
            caption = dict(alt)
            first = n
            if blocks and blocks[-1]["type"] == "paragraph" and blocks[-1]["text"] == alt["text"]:
                previous = blocks.pop()
                first = previous["source_lines"][0] - 1
                caption = {k: previous[k] for k in ["text", "text_utf16_length", "runs"]}
            path = (markdown_path.parent / image.group(2)).resolve()
            try: relative = path.relative_to(root.resolve()).as_posix()
            except ValueError: raise ValueError("Figure must be inside this self-contained project: " + image.group(2))
            exists = path.is_file()
            width, height = png_size(path) if exists else (0, 0)
            max_height = {1: 2.8, 2: 3.8, 3: 3.3, 4: 2.5}.get(figure, 3.8) * 72
            scale = min(6.2 * 72 / width, max_height / height) if exists else None
            add("figure", first, n, ordinal=figure, local_path=relative, alt_text=alt["text"],
                caption=caption, native_insert_required=True, placeholder=f"[[V1_FIGURE_{figure:03d}]]",
                exists=exists, sha256=digest(path) if exists else None,
                pixels=[width, height] if exists else None,
                object_size_pt={"width": round(width * scale, 4), "height": round(height * scale, 4)} if exists else None,
                caption_placement="after_image", keep_image_with_caption=True)
            n += 1
            continue
        if n + 1 < len(lines) and table_separator(lines[n + 1]):
            rows = [split_row(line)]
            separators = split_row(lines[n + 1])
            end = n + 2
            while end < len(lines) and lines[end].strip().startswith("|"):
                rows.append(split_row(lines[end]))
                end += 1
            columns = len(rows[0])
            if len(separators) != columns or any(len(row) != columns for row in rows):
                raise ValueError(f"Nonrectangular table at line {n + 1}")
            table += 1
            add("table", n, end - 1, ordinal=table, row_count=len(rows), column_count=columns,
                header_row_count=1, native_insert_required=True, placeholder=f"[[V1_TABLE_{table:03d}]]",
                column_alignment=["CENTER" if c.startswith(":") and c.endswith(":") else "END" if c.endswith(":") else "START" for c in separators],
                rows=[[inline(cell, sources) for cell in row] for row in rows])
            n = end
            continue
        item = re.match(r"^(?:(\d+)[.)]|([-*]))\s+(.+)$", line)
        if item:
            add("list_item", n, n, ordered=item.group(1) is not None,
                source_number=int(item.group(1)) if item.group(1) else None,
                native_list_required=True, **inline(item.group(3), sources))
            n += 1
            continue
        end = n + 1
        while end < len(lines) and not special(end): end += 1
        add("paragraph", n, end - 1, **inline("\n".join(lines[n:end]), sources))
        n = end
    if equation != len(EXPECTED_EQUATIONS):
        raise ValueError(f"Report contains {equation} equations; exactly 22 retained native equation slots are required")
    for ordinal, block in enumerate(blocks, 1): block["id"] = f"b{ordinal:03d}"
    return blocks


def native_inventory(path: Path | None) -> dict:
    if path is None:
        return {"inspected": False, "required_equation_count": 22,
                "note": "The archived text readback does not expose equation objects. Inspect all copied native tabs before writes."}
    data = json.loads(path.read_text())
    inventory = []
    tabs = data.get("tabs", [])

    def visit(tab: dict) -> None:
        body = tab.get("documentTab", tab)
        tab_id = tab.get("tabProperties", {}).get("tabId", tab.get("tabId"))
        for element in body.get("body", {}).get("content", []):
            equations = [x for x in element.get("paragraph", {}).get("elements", []) if "equation" in x]
            if equations:
                if len(equations) != 1: raise ValueError("Expected one native equation per preserved paragraph")
                inventory.append({"ordinal": len(inventory) + 1, "tab_id": tab_id,
                    "native_element_type": "equation", "equation_utf16_length": equations[0]["endIndex"] - equations[0]["startIndex"],
                    "paragraph_utf16_length": element["endIndex"] - element["startIndex"],
                    "formula_payload_exposed": bool(equations[0]["equation"])})
        for child in tab.get("childTabs", []): visit(child)

    for tab in tabs: visit(tab)
    if len(inventory) != 22: raise ValueError(f"Native template has {len(inventory)} equation paragraphs, expected 22")
    return {"inspected": True, "readback_sha256": digest(path), "document_id": data.get("documentId"),
            "revision_id_at_inspection": data.get("revisionId"), "equation_count": len(inventory),
            "equations": inventory, "stored_write_indexes": False,
            "formula_verification_limit": "Connector exposes equation objects but not their formula contents. Preserve them by native copy; verify rendered formulas against the LaTeX ordinal references."}


def build_plan(root: Path, native_readback: Path | None = None) -> dict:
    root = root.resolve()
    md_path = root / "report/report.md"
    markdown = md_path.read_text()
    template_path = root / "evidence/v0_report_readback.json"
    template = json.loads(template_path.read_text())
    blocks = parse_markdown(markdown, root, md_path)
    counts = Counter(b["type"] for b in blocks)
    segments = [{"ordinal": 0, "after_equation": None, "before_equation": 1, "block_ids": [], "text_with_placeholders": "", "paragraphs": []}]
    for block in blocks:
        if block["type"] == "native_equation":
            k = block["ordinal"]
            segments.append({"ordinal": k, "after_equation": k, "before_equation": k + 1 if k < 22 else None,
                             "block_ids": [], "text_with_placeholders": "", "paragraphs": []})
            continue
        segment = segments[-1]
        segment["block_ids"].append(block["id"])
        paragraphs = [(block.get("text", block.get("placeholder", "")), block["type"], block.get("runs", []))]
        if block["type"] == "figure":
            paragraphs.append((block["caption"]["text"], "figure_caption", block["caption"]["runs"]))
        for text, role, runs in paragraphs:
            offset = utf16(segment["text_with_placeholders"])
            segment["paragraphs"].append({"block_id": block["id"], "role": role, "text": text,
                "start_utf16": offset, "end_utf16": offset + utf16(text), "runs": runs})
            segment["text_with_placeholders"] += text + "\n"
    blockers = []
    if counts["figure"] != 4: blockers.append(f"Expected four actual figures; Markdown currently contains {counts['figure']}.")
    if "Draft figure pending:" in markdown: blockers.append("The Markdown still contains draft figure placeholders.")
    for block in blocks:
        if block["type"] == "figure" and not block["exists"]: blockers.append("Missing actual figure: " + block["local_path"])
    receipt_path = root / "report/build_receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("draft"): blockers.append("Report build_receipt.json still marks the report as draft.")
        if receipt.get("outputs", {}).get("report/report.md") != digest(md_path): blockers.append("Report Markdown does not match its build receipt.")
    hashes = {"report/report.md": digest(md_path), "evidence/v0_report_readback.json": digest(template_path),
              "scripts/build_native_report_plan.py": digest(Path(__file__))}
    if receipt_path.exists(): hashes["report/build_receipt.json"] = digest(receipt_path)
    hashes.update({b["local_path"]: b["sha256"] for b in blocks if b["type"] == "figure" and b["exists"]})
    date_match = re.search(r"\b\d{1,2} [A-Z][a-z]+ \d{4}\b", markdown[:500])
    report_date = date_match.group(0) if date_match else "19 November 2026"
    return {"schema": "native-google-docs-report-plan-v1", "source_markdown": "report/report.md",
        "input_hashes": hashes, "content_ready_for_native_application": not blockers,
        "content_blockers": blockers, "counts": dict(counts),
        "template": {"document_id": template["documentId"], "document_url": template["document_url"],
            "copy_natively": True, "retained_equation_count": 22, "native_inventory": native_inventory(native_readback)},
        "auxiliary_scoped_text_updates": [
            {"scope": "header", "old_exact_text": "Beam wall mount v0    Engineering screening report",
             "new_exact_text": "Beam wall mount v1    Engineering screening report", "preserve_style": True},
            {"scope": "footer", "old_exact_text": "17 November 2026   |   ",
             "new_exact_text": report_date + "   |   ", "preserve_native_page_number_field": True}
        ],
        "application_policy": {
            "destination": "Create a native copy in the ChatGPT folder; never edit the retained v0 source.",
            "equations": "Keep the 22 actual equation paragraphs, including their paragraph-ending newline, in existing order. LaTeX is audit text only.",
            "deletions": "Derive non-equation body spans from fresh copied-document readback; delete in descending order while preserving equation ranges and the final structural newline.",
            "insertions": "Insert the 23 segments around the retained equations. Their placeholder paragraphs mark locations for actual native tables and inline images.",
            "indexes": "All external write indexes are UTF-16 units and must be derived from current connector readback. Relative offsets in this plan are only inside inserted segment text.",
            "tables": "Use native insertTable, read returned cell paragraph positions, and fill cells in descending index order. Do not insert Markdown pipes as the final table.",
            "figures": "Resolve each project-relative local path to an absolute upload path. Insert an inline image with the supplied aspect-preserving object size; caption follows it.",
            "formatting": "Use existing template named styles. Apply heading named styles, body spacing, inline bold/code/link spans and native list bullets; reset unintended inherited character styling.",
            "concurrency": "Use requiredRevisionId for guarded writes; reconcile any conflicting revision before continuing.",
            "verification": "Read all final tabs once and verify 22 native equations, all planned native tables and four inline figures, exact text and hyperlinks, no placeholders or stale v0 prose. Export PDF and inspect all pages and formulas."
        },
        "blocks": blocks, "segments": segments,
        "expected_final_native_structure": {"equation_paragraphs": 22, "tables": counts["table"], "inline_images": 4,
            "heading_texts": [b["text"] for b in blocks if b["type"] == "heading"],
            "placeholder_tokens_must_be_absent": [b["placeholder"] for b in blocks if "placeholder" in b],
            "latex_must_not_be_inserted_as_body_text": True},
        "network_writes_performed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--native-template", type=Path, help="Fresh, sanitized connector readback of the retained v0 native template")
    parser.add_argument("--output", type=Path, help="Default: ROOT/report/native_report_plan.json")
    parser.add_argument("--allow-draft", action="store_true", help="Write an explicitly blocked development plan outside report/")
    args = parser.parse_args()
    retained_native = args.root / 'evidence/v0_native_template.json'
    native_template = args.native_template or (retained_native if retained_native.is_file() else None)
    plan = build_plan(args.root, native_template)
    output = args.output or args.root / "report/native_report_plan.json"
    if not plan["content_ready_for_native_application"] and not args.allow_draft:
        print(json.dumps({"status": "BLOCKED", "reasons": plan["content_blockers"]}, indent=2))
        return 2
    if not plan["content_ready_for_native_application"] and output.resolve().parent == (args.root / "report").resolve():
        raise ValueError("Draft plans must be written outside report/ using --output")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "content_ready": plan["content_ready_for_native_application"],
                      "counts": plan["counts"], "segments": len(plan["segments"]),
                      "native_template_inspected": plan["template"]["native_inventory"]["inspected"]}, indent=2))
    return 0 if plan["content_ready_for_native_application"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
