import re
import unicodedata
from typing import Any

from .schemas import NameCleanupPack, NameCleanupPackValidation


def _literal_replacer(value: str):
    def replace(_match: re.Match[str]) -> str:
        return value
    return replace


def validate_cleanup_pack(pack: NameCleanupPack) -> NameCleanupPackValidation:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    replacements: dict[tuple[str, str], str] = {}
    for rule in pack.rules:
        if rule.id in seen:
            errors.append(f"cleanup.duplicate_rule:{rule.id}")
        seen.add(rule.id)
        if not rule.pattern:
            errors.append(f"cleanup.empty_pattern:{rule.id}")
        if rule.kind == "regex_replace":
            try:
                re.compile(rule.pattern)
            except re.error:
                errors.append(f"cleanup.invalid_regex:{rule.id}")
        key = (rule.kind, rule.pattern.casefold())
        if key in replacements and replacements[key] != rule.replacement:
            warnings.append(f"cleanup.conflicting_replacement:{rule.id}")
        replacements[key] = rule.replacement
    for pattern in pack.protected_regex:
        try:
            re.compile(pattern)
        except re.error:
            errors.append("cleanup.invalid_protected_regex")
    if not pack.rules:
        errors.append("cleanup.empty_pack")
    return NameCleanupPackValidation(
        valid=not errors,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        rule_count=len(pack.rules),
    )


def apply_cleanup_packs(
    stem: str,
    relative_path: str,
    extension: str,
    packs: list[dict[str, Any]],
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    current = stem
    applied: set[tuple[str, str, str]] = set()
    for raw_pack in packs:
        pack = NameCleanupPack.model_validate(raw_pack)
        protected = (
            current.casefold() in {item.casefold() for item in pack.protected_names}
            or any(item.casefold() in current.casefold() for item in pack.protected_keywords)
            or any(re.search(pattern, current, re.IGNORECASE) for pattern in pack.protected_regex)
        )
        if protected:
            reasons.append(f"cleanup.protected:{pack.id}")
            continue
        for rule in sorted(pack.rules, key=lambda item: item.order):
            if not rule.enabled:
                continue
            if rule.extensions and extension.casefold() not in {
                item.casefold() for item in rule.extensions
            }:
                continue
            if rule.path_contains and not any(
                item.casefold() in relative_path.casefold() for item in rule.path_contains
            ):
                continue
            signature = (rule.kind, rule.pattern.casefold(), rule.replacement)
            if signature in applied:
                continue
            applied.add(signature)
            before = current
            if rule.kind == "remove_contains":
                current = re.sub(re.escape(rule.pattern), "", current, flags=re.IGNORECASE)
            elif rule.kind == "remove_prefix" and current.casefold().startswith(rule.pattern.casefold()):
                current = current[len(rule.pattern):]
            elif rule.kind == "remove_suffix" and current.casefold().endswith(rule.pattern.casefold()):
                current = current[:-len(rule.pattern)]
            elif rule.kind == "literal_replace":
                current = re.sub(
                    re.escape(rule.pattern),
                    _literal_replacer(rule.replacement),
                    current,
                    flags=re.IGNORECASE,
                )
            elif rule.kind == "regex_replace":
                current = re.sub(rule.pattern, rule.replacement, current)
            if current != before:
                reasons.append(f"cleanup.rule:{pack.id}:{pack.version}:{rule.id}")
                if rule.stop_on_match:
                    break
        if pack.normalize_width:
            current = unicodedata.normalize("NFKC", current)
        if pack.deduplicate_words:
            current = re.sub(r"(?i)\b([^\W\d_]+)(?:\s+\1)+\b", r"\1", current)
        if pack.normalize_separators:
            current = re.sub(r"[._]+", " ", current)
        current = re.sub(r"\s+", " ", current).strip(" ._-")
        if len(current) > pack.max_name_length:
            warnings.append(f"cleanup.name_too_long:{pack.id}")
    return current, reasons, warnings


def cleanup_pack_dict(pack: NameCleanupPack) -> dict[str, Any]:
    return pack.model_dump(mode="json")


def _rule(id: str, name: str, kind: str, pattern: str, order: int, replacement: str = ""):
    return {
        "id": id, "name": name, "description": "", "enabled": True,
        "order": order, "kind": kind, "pattern": pattern,
        "replacement": replacement, "extensions": [], "path_contains": [],
        "stop_on_match": False, "examples": [],
    }


BUILTIN_CLEANUP_PACKS = [
    NameCleanupPack(id="general-advertisement-cleanup", version="1", name="General advertisement cleanup", description="Remove common advertisement and promotion words.", rules=[_rule("general.ad", "Advertisement", "remove_contains", "广告", 0), _rule("general.promo", "Promotion", "remove_contains", "推广", 1), _rule("general.resources", "More resources", "remove_contains", "更多资源", 2)]),
    NameCleanupPack(id="bt-name-cleanup", version="1", name="BT download name cleanup", description="Remove common BT download promotion markers.", rules=[_rule("bt.website", "Website brackets", "regex_replace", r"\[(?:www\.)?[^\]]+\.(?:com|net|org|cn)\]", 0), _rule("bt.online", "Watch online", "remove_contains", "在线观看", 1)]),
    NameCleanupPack(id="website-domain-cleanup", version="1", name="Website and domain cleanup", description="Remove website and domain markers from names.", rules=[_rule("domain.url", "URL", "regex_replace", r"https?://\S+", 0), _rule("domain.name", "Domain", "regex_replace", r"(?i)(?:www\.)?[a-z0-9-]+\.(?:com|net|org|cn)", 1)]),
    NameCleanupPack(id="media-name-normalization", version="1", name="Media name normalization", description="Normalize common media separators.", rules=[_rule("media.separator", "Release separator", "literal_replace", "_", 0, " ")]),
    NameCleanupPack(id="image-name-normalization", version="1", name="Image name normalization", description="Normalize camera and exported image names.", rules=[_rule("image.copy", "Copy suffix", "remove_suffix", " copy", 0)]),
]
