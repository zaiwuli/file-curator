"""Deterministic metadata rules for junk and advertisement candidates."""

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from .processors import ProcessingContext

JunkAction = Literal["keep", "review", "quarantine"]


@dataclass(frozen=True)
class JunkRule:
    id: str
    name: str
    description: str
    action: JunkAction
    score: int = 0
    extensions: tuple[str, ...] = ()
    filename_contains: tuple[str, ...] = ()
    filename_regex: tuple[str, ...] = ()
    path_contains: tuple[str, ...] = ()
    max_size: int | None = None
    min_size: int | None = None
    empty_only: bool = False
    enabled: bool = True
    order: int = 0
    stop_on_match: bool = False


@dataclass(frozen=True)
class JunkRulePack:
    id: str
    version: str
    name: str
    description: str
    rules: tuple[JunkRule, ...]
    protected_extensions: tuple[str, ...] = (".srt", ".ass", ".ssa", ".nfo")
    protected_names: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()
    source: Literal["built_in", "personal", "snapshot"] = "built_in"


@dataclass(frozen=True)
class JunkEvidence:
    rule_id: str
    action: JunkAction
    score: int
    reason: str
    matched_value: str


@dataclass(frozen=True)
class JunkEvaluation:
    candidate: bool
    action: JunkAction
    score: int
    evidence: tuple[JunkEvidence, ...]
    protected: bool


def _rule_matches(rule: JunkRule, context: ProcessingContext) -> str | None:
    name = context.original_name.casefold()
    relative_path = context.relative_path.casefold()
    extension = context.extension.casefold()
    if rule.extensions and extension not in {value.casefold() for value in rule.extensions}:
        return None
    if rule.filename_contains:
        matched = next((value for value in rule.filename_contains if value.casefold() in name), None)
        if matched is None:
            return None
        value = matched
    else:
        value = extension or context.original_name
    if rule.filename_regex:
        matched_regex = next((pattern for pattern in rule.filename_regex if re.search(pattern, context.original_name, re.I)), None)
        if matched_regex is None:
            return None
        value = matched_regex
    if rule.path_contains and not any(value.casefold() in relative_path for value in rule.path_contains):
        return None
    if rule.max_size is not None and context.size > rule.max_size:
        return None
    if rule.min_size is not None and context.size < rule.min_size:
        return None
    if rule.empty_only and context.size != 0:
        return None
    return value


def evaluate_junk(context: ProcessingContext, pack: JunkRulePack) -> JunkEvaluation:
    protected = (
        context.extension.casefold() in {value.casefold() for value in pack.protected_extensions}
        or any(value.casefold() in context.original_name.casefold() for value in pack.protected_names)
        or any(value.casefold() in context.relative_path.casefold() for value in pack.protected_paths)
    )
    evidence: list[JunkEvidence] = []
    for rule in sorted(pack.rules, key=lambda item: item.order):
        if not rule.enabled:
            continue
        matched_value = _rule_matches(rule, context)
        if matched_value is None:
            continue
        if rule.action == "keep":
            return JunkEvaluation(False, "keep", 0, (), True)
        if protected:
            continue
        evidence.append(JunkEvidence(rule.id, rule.action, rule.score, f"junk.{rule.id}", matched_value))
        if rule.stop_on_match:
            break
    text_signals = context.fields.get("text_signals", [])
    if not protected and text_signals:
        evidence.append(JunkEvidence(
            "text.signal",
            "quarantine" if "promotion" in text_signals else "review",
            55 if "promotion" in text_signals else 35,
            "junk.text.signal",
            ",".join(text_signals),
        ))
    duplicate_count = int(context.fields.get("hash_duplicate_count", 0))
    directory_count = int(context.fields.get("hash_directory_count", 0))
    if not protected and context.size <= 1_000_000 and duplicate_count >= 3 and directory_count >= 3:
        evidence.append(JunkEvidence(
            "repeated.hash",
            "quarantine",
            60,
            "junk.repeated.hash",
            f"{duplicate_count}:{directory_count}",
        ))
    score = min(100, sum(item.score for item in evidence))
    if any(item.action == "quarantine" for item in evidence):
        action: JunkAction = "quarantine"
    elif any(item.action == "review" for item in evidence):
        action = "review"
    else:
        action = "keep"
    return JunkEvaluation(bool(evidence), action, score, tuple(evidence), protected)


def junk_pack_from_dict(value: dict[str, Any]) -> JunkRulePack:
    rules = tuple(
        JunkRule(
            id=str(item["id"]),
            name=str(item["name"]),
            description=str(item.get("description", "")),
            action=item.get("action", "review"),
            score=int(item.get("score", 0)),
            extensions=tuple(item.get("extensions", ())),
            filename_contains=tuple(item.get("filename_contains", ())),
            filename_regex=tuple(item.get("filename_regex", ())),
            path_contains=tuple(item.get("path_contains", ())),
            max_size=item.get("max_size"),
            min_size=item.get("min_size"),
            empty_only=bool(item.get("empty_only", False)),
            enabled=bool(item.get("enabled", True)),
            order=int(item.get("order", 0)),
            stop_on_match=bool(item.get("stop_on_match", False)),
        )
        for item in value.get("rules", ())
    )
    return JunkRulePack(
        id=str(value["id"]),
        version=str(value.get("version", "1")),
        name=str(value["name"]),
        description=str(value.get("description", "")),
        rules=rules,
        protected_extensions=tuple(value.get("protected_extensions", ())),
        protected_names=tuple(value.get("protected_names", ())),
        protected_paths=tuple(value.get("protected_paths", ())),
        source=value.get("source", "snapshot"),
    )


def evaluate_junk_packs(
    context: ProcessingContext, packs: tuple[JunkRulePack, ...]
) -> JunkEvaluation:
    if not packs:
        return JunkEvaluation(False, "keep", 0, (), False)
    combined_rules = tuple(
        replace(
            rule,
            id=f"{pack.id}:{rule.id}",
            order=pack_order * 10_000 + rule_order,
        )
        for pack_order, pack in enumerate(packs)
        for rule_order, rule in enumerate(sorted(pack.rules, key=lambda item: item.order))
    )
    combined = JunkRulePack(
        id="combined",
        version="snapshot",
        name="Combined junk rules",
        description="",
        rules=combined_rules,
        protected_extensions=tuple(
            value for pack in packs for value in pack.protected_extensions
        ),
        protected_names=tuple(value for pack in packs for value in pack.protected_names),
        protected_paths=tuple(value for pack in packs for value in pack.protected_paths),
        source="snapshot",
    )
    return evaluate_junk(context, combined)


DEFAULT_JUNK_PACK = JunkRulePack(
    id="bt-advertisement-and-junk",
    version="1.0.0",
    name="BT advertisements and junk",
    description="Metadata-only rules for incomplete downloads, links, promotion files, and suspicious small attachments.",
    rules=(
        JunkRule("incomplete.download", "Incomplete download", "Temporary or incomplete download extension.", "quarantine", 70, extensions=(".tmp", ".part", ".download", ".crdownload")),
        JunkRule("link.file", "Internet link file", "A shortcut or URL file is usually a promotion pointer.", "quarantine", 80, extensions=(".url", ".website", ".lnk")),
        JunkRule("ad.keyword", "Advertisement keyword", "The filename contains a common promotion marker.", "quarantine", 55, filename_contains=("广告", "推广", "宣传", "最新网址", "更多资源", "扫码", "关注", "promo", "download more")),
        JunkRule("ad.domain", "Website marker", "The filename contains a URL or domain marker.", "review", 45, filename_regex=(r"https?://", r"www\.", r"[a-z0-9-]+\.(?:com|net|org|cc|tv|me)")),
        JunkRule("empty.file", "Empty file", "The file has no data.", "review", 35, empty_only=True),
        JunkRule("tiny.text", "Tiny promotion text", "A small text or HTML attachment can contain a promotion link.", "review", 35, extensions=(".txt", ".html", ".htm"), max_size=100_000),
        JunkRule("tiny.media", "Tiny unrelated media", "An unusually small image or video is a review candidate.", "review", 20, extensions=(".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mkv"), max_size=1_000_000),
        JunkRule("sample.marker", "Sample or trailer marker", "The name suggests a sample or trailer rather than the main file.", "review", 25, filename_contains=("sample", "trailer", "preview")),
    ),
)


def junk_pack_dict(pack: JunkRulePack) -> dict[str, Any]:
    return {
        "id": pack.id,
        "version": pack.version,
        "name": pack.name,
        "description": pack.description,
        "protected_extensions": list(pack.protected_extensions),
        "protected_names": list(pack.protected_names),
        "protected_paths": list(pack.protected_paths),
        "source": pack.source,
        "read_only": pack.source == "built_in",
        "current_version": int(pack.version.split(".")[0]) if pack.version.split(".")[0].isdigit() else 1,
        "rules": [
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "enabled": rule.enabled,
                "order": position,
                "action": rule.action,
                "score": rule.score,
                "extensions": list(rule.extensions),
                "filename_contains": list(rule.filename_contains),
                "filename_regex": list(rule.filename_regex),
                "path_contains": list(rule.path_contains),
                "max_size": rule.max_size,
                "min_size": rule.min_size,
                "empty_only": rule.empty_only,
                "stop_on_match": rule.stop_on_match,
            }
            for position, rule in enumerate(pack.rules)
        ],
    }
