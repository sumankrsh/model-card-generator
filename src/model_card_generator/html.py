"""Turn the card's Markdown into one self-contained HTML page.

Only the Markdown this tool writes needs to be supported: headings, paragraphs,
a block quote, bullet lists, tables and inline bold, italics and code. The page
has no scripts and makes no external requests.
"""

from __future__ import annotations

import html
import re

CSS = """
:root{--bg:#faf8f4;--fg:#22201c;--muted:#6b665d;--line:#e2ddd3;--card:#fff;--accent:#b4532a;
--high:#b42318;--high-bg:#fdecea;--med:#8a5a00;--med-bg:#fdf3dc;--low:#475467;--low-bg:#eef1f5;--ok:#1d6b3a}
@media (prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8e1;--muted:#a59f94;--line:#35322d;--card:#22201d;
--accent:#e08a5f;--high:#ff8a80;--high-bg:#3a1f1c;--med:#f2c46b;--med-bg:#352a14;--low:#b8c2d0;--low-bg:#262a31;--ok:#7bd69a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 16px}
h2{font-size:1.3rem;margin:40px 0 12px;padding-top:12px;border-top:1px solid var(--line)}
h3{font-size:1.05rem;margin:24px 0 8px;color:var(--muted)}
blockquote{margin:0 0 16px;padding:12px 16px;background:var(--card);border-left:4px solid var(--accent);border-radius:4px}
code{font:0.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--card);
padding:1px 4px;border-radius:3px;border:1px solid var(--line);word-break:break-all}
.scroll{overflow-x:auto;margin:8px 0 12px}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:0.92rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted)}
.sev{display:inline-block;padding:1px 8px;border-radius:10px;font-size:0.82rem;font-weight:600}
.sev-high{color:var(--high);background:var(--high-bg)}.sev-medium{color:var(--med);background:var(--med-bg)}
.sev-low{color:var(--low);background:var(--low-bg)}.fail{color:var(--high);font-weight:700}.pass{color:var(--ok)}
ul{padding-left:22px}li{margin:3px 0}
footer{margin-top:48px;color:var(--muted);font-size:0.85rem}
"""


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w])", r"<em>\1</em>", out)
    return out


def cell(text: str, severity_column: bool = False) -> str:
    raw = text.replace("\\|", "|").strip()
    if severity_column and raw in {"high", "medium", "low"}:
        return f'<span class="sev sev-{raw}">{raw}</span>'
    if raw == "**fail**":
        return '<span class="fail">fail</span>'
    if raw == "pass":
        return '<span class="pass">pass</span>'
    return inline(raw)


def split_row(line: str) -> list[str]:
    inner = line.strip()[1:-1]
    return [c for c in re.split(r"(?<!\\)\|", inner)]


def markdown_to_html(md: str, title: str) -> str:
    lines = md.splitlines()
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level = len(h.group(1))
            text = h.group(2)
            anchor = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            body.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            i += 1
            continue
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> "))
                i += 1
            body.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            head = split_row(rows[0])
            out = ['<div class="scroll"><table><thead><tr>']
            out += [f"<th>{inline(c.strip())}</th>" for c in head]
            out.append("</tr></thead><tbody>")
            sev = [c.strip() == "Severity" for c in head]
            for r in rows[2:]:
                cells = split_row(r)
                out.append(
                    "<tr>"
                    + "".join(f"<td>{cell(c, sev[i] if i < len(sev) else False)}</td>" for i, c in enumerate(cells))
                    + "</tr>"
                )
            out.append("</tbody></table></div>")
            body.append("".join(out))
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            body.append("<ul>" + "".join(items) + "</ul>")
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|>|\||- )", lines[i]):
            para.append(lines[i])
            i += 1
        body.append(f"<p>{inline(' '.join(para))}</p>")
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body><main>{''.join(body)}<footer>Self-contained page: no scripts, no external requests.</footer></main></body></html>\n"
    )
