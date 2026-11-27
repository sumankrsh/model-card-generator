"""Check a Markdown model card for the sections a profile requires.

Works on any Markdown file, whether this tool wrote it or a person did.
Each heading is matched to the section whose pattern covers most of it, so
"Validation data" counts as evaluation data and "Model validation" as
independent validation. A section passes when its text (including any
sub-sections) has at least a few words and doesn't start with a placeholder
such as "TBD" or "Not provided".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .profiles import SECTIONS, Profile

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
PLACEHOLDER = re.compile(
    r"^\W*(tbd|tbc|todo|to do|n/?a|none|not provided|not applicable|to be (completed|confirmed|added|written)"
    r"|coming soon|lorem ipsum|placeholder|fill (this )?in|\[fill|<fill|\?\?\?|xxx)\b",
    re.IGNORECASE,
)
MIN_WORDS = 3


@dataclass
class Heading:
    level: int
    text: str
    line: int
    body: str = ""


@dataclass
class SectionResult:
    key: str
    title: str
    reference: str
    status: str  # "ok", "missing", "empty", "placeholder"
    heading: str | None = None
    line: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class CheckResult:
    profile: str
    path: str
    results: list[SectionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> list[SectionResult]:
        return [r for r in self.results if not r.ok]


def normalise(text: str) -> str:
    text = re.sub(r"[`*_\[\]()]", "", text).lower()
    text = re.sub(r"^\s*(\d+(\.\d+)*\.?|[ivx]+\.)\s+", "", text)  # "3.1 Metrics", "IV. Data"
    return re.sub(r"\s+", " ", text.replace("&", "and")).strip(" :.-")


def parse_headings(markdown: str) -> list[Heading]:
    lines = markdown.splitlines()
    heads: list[Heading] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        m = None if in_fence else HEADING.match(line)
        if m:
            heads.append(Heading(len(m.group(1)), m.group(2), i))
    for n, h in enumerate(heads):
        end = len(lines)
        for later in heads[n + 1 :]:
            if later.level <= h.level:
                end = later.line - 1
                break
        h.body = "\n".join(lines[h.line : end])
    return heads


def classify(heading: str) -> str | None:
    """The section key whose pattern matches the longest part of this heading."""
    text = normalise(heading)
    best: tuple[int, str] | None = None
    for key, sec in SECTIONS.items():
        if text == sec.title.lower():
            return key
        for pat in sec.patterns:
            m = re.search(rf"\b(?:{pat})\b", text)
            if m and (best is None or len(m.group(0)) > best[0]):
                best = (len(m.group(0)), key)
    return best[1] if best else None


def body_status(body: str) -> str:
    text = "\n".join(line for line in body.splitlines() if not HEADING.match(line))
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    plain = re.sub(r"[|#>*_`\-:]+", " ", text).strip()
    words = re.findall(r"[A-Za-z0-9][\w.%/'-]*", plain)
    if len(words) < MIN_WORDS:
        return "placeholder" if PLACEHOLDER.match(plain) else "empty"
    if PLACEHOLDER.match(plain):
        return "placeholder"
    return "ok"


def check_markdown(markdown: str, profile: Profile, path: str = "<card>") -> CheckResult:
    heads = parse_headings(markdown)
    if any(h.level >= 2 for h in heads):
        heads = [h for h in heads if h.level >= 2]
    found: dict[str, list[Heading]] = {}
    for h in heads:
        key = classify(h.text)
        if key:
            found.setdefault(key, []).append(h)
    result = CheckResult(profile.name, path)
    for req in profile.requirements:
        sec = SECTIONS[req.section]
        hs = found.get(req.section)
        if not hs:
            result.results.append(SectionResult(sec.key, sec.title, req.reference, "missing"))
            continue
        statuses = [body_status(h.body) for h in hs]
        best = next((i for i, s in enumerate(statuses) if s == "ok"), 0)
        h = hs[best]
        result.results.append(SectionResult(sec.key, sec.title, req.reference, statuses[best], h.text, h.line))
    return result
