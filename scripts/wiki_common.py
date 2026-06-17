from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = ROOT / "wiki"

REQUIRED_FRONTMATTER = {"status", "updated", "confidence", "expires", "sources", "tags"}
ALLOWED_CONFIDENCE = {"observed", "verified", "decision"}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"BEGIN (RSA|OPENSSH) PRIVATE KEY"),
    re.compile(r"\b(TOKEN|PASSWORD|SECRET)=\S+"),
]
HOME_PATH_RE = re.compile(r"(?:/" r"Users|/home|/root)/[^\s`'\")]+")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass
class WikiPage:
    path: Path
    rel_path: str
    wiki_path: str
    frontmatter: dict[str, Any]
    body: str
    text: str


@dataclass
class Finding:
    level: str
    path: str
    message: str


def normalize_wiki_dir(wiki_dir: Path) -> Path:
    if not wiki_dir.is_absolute():
        wiki_dir = ROOT / wiki_dir
    return wiki_dir.resolve()


def iter_markdown_files(wiki_dir: Path = WIKI_DIR) -> list[Path]:
    wiki_dir = normalize_wiki_dir(wiki_dir)
    if not wiki_dir.exists():
        return []
    raw_sessions_dir = (wiki_dir / "sessions").resolve()
    return sorted(
        path
        for path in wiki_dir.rglob("*.md")
        if raw_sessions_dir not in path.resolve().parents
    )


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        data = {}
    return data, body


def load_pages(wiki_dir: Path = WIKI_DIR) -> list[WikiPage]:
    wiki_dir = normalize_wiki_dir(wiki_dir)
    pages: list[WikiPage] = []
    for path in iter_markdown_files(wiki_dir):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        pages.append(
            WikiPage(
                path=path,
                rel_path=path.relative_to(ROOT).as_posix(),
                wiki_path=path.relative_to(wiki_dir).as_posix(),
                frontmatter=frontmatter,
                body=body,
                text=text,
            )
        )
    return pages


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def is_external_link(target: str) -> bool:
    return (
        target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
        or target.startswith("#")
    )


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def resolve_markdown_link(page: WikiPage, target: str) -> Path | None:
    target = strip_anchor(target.strip())
    if not target or is_external_link(target):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return (page.path.parent / target).resolve()


def source_exists(source: str) -> bool:
    if is_external_link(source):
        return True
    return (ROOT / strip_anchor(source)).exists()


def page_budget(wiki_path: str) -> int | None:
    if wiki_path == "index.md":
        return 300
    if wiki_path.startswith("system/"):
        return 250
    if wiki_path.startswith("context-packs/"):
        return 250
    if wiki_path.startswith("concepts/"):
        return 250
    if wiki_path.startswith("decisions/"):
        return 150
    return None


def has_context_contract(page: WikiPage) -> bool:
    if not page.wiki_path.startswith("context-packs/"):
        return True
    required = [
        "## Contract",
        "Purpose:",
        "Scope:",
        "Read triggers:",
        "Source of truth:",
        "Verification references:",
        "Stop conditions:",
        "Owner and expiry:",
    ]
    body_lower = page.body.lower()
    return all(item.lower() in body_lower for item in required)


def collect_links(pages: list[WikiPage], wiki_dir: Path = WIKI_DIR) -> set[str]:
    wiki_dir = normalize_wiki_dir(wiki_dir)
    linked: set[str] = set()
    for page in pages:
        for target in MARKDOWN_LINK_RE.findall(page.body):
            resolved = resolve_markdown_link(page, target)
            if resolved and resolved.exists() and wiki_dir.resolve() in resolved.parents:
                linked.add(resolved.relative_to(ROOT).as_posix())
    return linked


def lint_pages(profile: str = "normal", wiki_dir: Path = WIKI_DIR) -> list[Finding]:
    wiki_dir = normalize_wiki_dir(wiki_dir)
    today = date.today()
    pages = load_pages(wiki_dir)
    findings: list[Finding] = []
    linked = collect_links(pages, wiki_dir)

    if not pages:
        return [Finding("error", wiki_dir.relative_to(ROOT).as_posix(), "wiki directory has no Markdown pages")]

    for page in pages:
        missing = REQUIRED_FRONTMATTER - set(page.frontmatter)
        if missing:
            findings.append(
                Finding("error", page.rel_path, f"missing frontmatter fields: {', '.join(sorted(missing))}")
            )

        confidence = page.frontmatter.get("confidence")
        if confidence is not None and confidence not in ALLOWED_CONFIDENCE:
            findings.append(Finding("error", page.rel_path, f"invalid confidence: {confidence}"))

        sources = page.frontmatter.get("sources")
        if not isinstance(sources, list) or not sources:
            findings.append(Finding("error", page.rel_path, "missing non-empty sources list"))
        else:
            for source in sources:
                if isinstance(source, str) and not source_exists(source):
                    findings.append(Finding("error", page.rel_path, f"source does not exist: {source}"))

        for pattern in SECRET_PATTERNS:
            if pattern.search(page.text):
                findings.append(Finding("error", page.rel_path, "possible secret pattern found"))

        if HOME_PATH_RE.search(page.text):
            findings.append(Finding("error", page.rel_path, "developer-specific absolute home path found"))

        for target in MARKDOWN_LINK_RE.findall(page.body):
            resolved = resolve_markdown_link(page, target)
            if resolved and not resolved.exists():
                findings.append(Finding("error", page.rel_path, f"broken markdown link: {target}"))

        expires = parse_date(page.frontmatter.get("expires"))
        if expires is None:
            findings.append(Finding("error", page.rel_path, "expires must be YYYY-MM-DD"))
        elif expires < today:
            level = "error" if profile == "autonomous" else "warning"
            findings.append(Finding(level, page.rel_path, f"page expired on {expires.isoformat()}"))
        elif expires <= today + timedelta(days=14):
            findings.append(Finding("warning", page.rel_path, f"page expires soon on {expires.isoformat()}"))

        budget = page_budget(page.wiki_path)
        if budget is not None:
            line_count = page.text.count("\n") + 1
            if line_count > budget:
                findings.append(Finding("warning", page.rel_path, f"page has {line_count} lines over budget {budget}"))

        if page.wiki_path.startswith("context-packs/"):
            if not page.frontmatter.get("owner"):
                findings.append(Finding("error", page.rel_path, "context pack missing owner"))
            if not has_context_contract(page):
                findings.append(Finding("error", page.rel_path, "context pack missing required contract sections"))
            if profile == "autonomous":
                body_lower = page.body.lower()
                if "verification references:" not in body_lower:
                    findings.append(Finding("error", page.rel_path, "autonomous profile requires verification references"))

        if (
            page.wiki_path != "index.md"
            and not page.wiki_path.startswith("drafts/")
            and page.rel_path not in linked
        ):
            findings.append(Finding("warning", page.rel_path, "orphan wiki page"))

    return findings


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("wiki checks passed")
        return
    for finding in findings:
        print(f"{finding.level.upper()}: {finding.path}: {finding.message}")


def has_errors(findings: list[Finding]) -> bool:
    return any(finding.level == "error" for finding in findings)
