import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, ClassVar


@dataclass(frozen=True)
class ProcessorManifest:
    id: str
    version: str
    category: str
    requires: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    default_enabled: bool = True
    score_weight: float = 0.0
    safety_class: str = "normal"
    option_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingContext:
    entry_id: str
    relative_path: str
    original_name: str
    parent_path: str
    extension: str
    size: int
    mtime_ns: int
    fields: dict[str, Any] = field(default_factory=dict)
    proposed_name: str | None = None
    proposed_parent: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProcessorResult:
    status: str = "matched"
    confidence_delta: float = 0.0
    fields: dict[str, Any] = field(default_factory=dict)
    proposed_name: str | None = None
    proposed_parent: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Processor(ABC):
    manifest: ClassVar[ProcessorManifest]

    @abstractmethod
    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        raise NotImplementedError


class DateExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_date",
        "1.0.0",
        "extract",
        provides=("date", "year", "month", "day"),
        score_weight=0.25,
    )
    pattern = re.compile(
        r"(?<!\d)(20\d{2})(?:[-_.]|\u5e74)(\d{1,2})(?:[-_.]|\u6708)(\d{1,2})(?:\u65e5)?(?!\d)"
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        match = self.pattern.search(context.original_name)
        if not match:
            return ProcessorResult(status="skipped")
        try:
            value = date(*(int(part) for part in match.groups()))
        except ValueError:
            return ProcessorResult(status="warning", warnings=["date.invalid"])
        return ProcessorResult(
            confidence_delta=self.manifest.score_weight,
            fields={
                "date": value.isoformat(),
                "year": f"{value.year:04d}",
                "month": f"{value.month:02d}",
                "day": f"{value.day:02d}",
            },
            reasons=["date.full_date_matched"],
        )


class IdentifierExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_identifier",
        "1.0.0",
        "extract",
        provides=("identifier",),
        score_weight=0.25,
        option_schema={"pattern": {"type": "string"}},
    )
    default_pattern = re.compile(r"(?i)(?<![A-Z0-9])([A-Z]{2,10}-\d{2,10})(?![A-Z0-9])")

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        pattern = re.compile(options.get("pattern", self.default_pattern.pattern), re.IGNORECASE)
        match = pattern.search(context.original_name)
        if not match:
            return ProcessorResult(status="skipped")
        identifier = match.group(1).upper()
        return ProcessorResult(
            confidence_delta=0.25,
            fields={"identifier": identifier},
            reasons=["identifier.pattern_matched"],
        )


class SequenceExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_sequence", "1.0.0", "extract", provides=("sequence",), score_weight=0.15
    )
    pattern = re.compile(r"(?i)(?:\((\d{1,3})\)|\b(?:part|pt|cd|ep)[ ._-]?(\d{1,3})\b)")

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        match = self.pattern.search(Path(context.original_name).stem)
        if not match:
            return ProcessorResult(status="skipped")
        number = int(match.group(1) or match.group(2))
        return ProcessorResult(
            confidence_delta=0.15, fields={"sequence": number}, reasons=["sequence.pattern_matched"]
        )


class QualityExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_quality", "1.0.0", "extract", provides=("resolution", "quality"), score_weight=0.1
    )
    pattern = re.compile(r"(?i)\b(720p|1080p|2160p|4k|web[- .]?dl|bluray|remux|hdr)\b")

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        values = [
            m.group(1).lower().replace(" ", "-")
            for m in self.pattern.finditer(context.original_name)
        ]
        if not values:
            return ProcessorResult(status="skipped")
        fields: dict[str, Any] = {"quality": values}
        resolution = next((v for v in values if v in {"720p", "1080p", "2160p", "4k"}), None)
        if resolution:
            fields["resolution"] = resolution
        return ProcessorResult(
            confidence_delta=0.1, fields=fields, reasons=["quality.marker_matched"]
        )


class ParentContextExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_parent_context", "1.0.0", "extract", provides=("parent_name",), score_weight=0.05
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        parent = Path(context.parent_path).name if context.parent_path else ""
        if not parent:
            return ProcessorResult(status="skipped")
        return ProcessorResult(
            confidence_delta=0.05,
            fields={"parent_name": parent},
            reasons=["context.parent_available"],
        )


class CustomRegexExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_regex",
        "1.0.0",
        "extract",
        score_weight=0.1,
        safety_class="advanced",
        option_schema={
            "pattern": {"type": "string"},
            "field": {"type": "string", "default": "custom"},
        },
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        pattern = options.get("pattern")
        field_name = options.get("field", "custom")
        if not pattern:
            return ProcessorResult(status="skipped")
        match = re.search(pattern, context.original_name)
        if not match:
            return ProcessorResult(status="skipped")
        value = match.groupdict().get(field_name) if match.groupdict() else match.group(1)
        return ProcessorResult(
            confidence_delta=0.1, fields={field_name: value}, reasons=["custom_regex.matched"]
        )


class NameNormalizer(Processor):
    manifest = ProcessorManifest(
        "normalize_name",
        "1.0.0",
        "normalize",
        provides=("proposed_name",),
        score_weight=0.1,
        option_schema={
            "remove_prefixes": {"type": "array", "items": {"type": "string"}},
            "replacements": {"type": "array", "items": {"type": "object"}},
            "invalid_replacement": {"type": "string", "default": "_"},
        },
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        path = Path(context.proposed_name or context.original_name)
        stem = unicodedata.normalize("NFC", path.stem)
        for prefix in options.get("remove_prefixes", []):
            if stem.lower().startswith(str(prefix).lower()):
                stem = stem[len(str(prefix)) :]
        for replacement in options.get("replacements", []):
            stem = re.sub(
                replacement.get("pattern", "(?!)"), replacement.get("replacement", ""), stem
            )
        stem = re.sub(r"\s+", " ", stem).strip(" ._-")
        invalid = r'[<>:"/\\|?*\x00-\x1f]'
        stem = re.sub(invalid, options.get("invalid_replacement", "_"), stem)
        if not stem:
            return ProcessorResult(status="warning", warnings=["name.empty_after_normalization"])
        new_name = stem + path.suffix.lower()
        if new_name == context.original_name:
            return ProcessorResult(status="skipped")
        return ProcessorResult(
            confidence_delta=0.1, proposed_name=new_name, reasons=["name.normalized"]
        )


class TemplateTarget(Processor):
    manifest = ProcessorManifest(
        "target_template",
        "1.0.0",
        "target",
        provides=("proposed_name", "proposed_parent"),
        safety_class="review",
        option_schema={
            "name_template": {"type": "string"},
            "parent_template": {"type": "string"},
        },
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        values = {
            **context.fields,
            "original_stem": Path(context.original_name).stem,
            "extension": context.extension.lstrip("."),
            "name": context.proposed_name or context.original_name,
        }
        warnings: list[str] = []
        try:
            name_template = options.get("name_template")
            parent_template = options.get("parent_template")
            name = name_template.format_map(values) if name_template else context.proposed_name
            if name and not Path(name).suffix:
                name += context.extension
            parent = (
                parent_template.format_map(values) if parent_template else context.proposed_parent
            )
        except KeyError as exc:
            warnings.append(f"template.missing_field:{exc.args[0]}")
            return ProcessorResult(status="review", warnings=warnings)
        return ProcessorResult(
            proposed_name=name, proposed_parent=parent, reasons=["target.template_rendered"]
        )


class JunkDetector(Processor):
    manifest = ProcessorManifest(
        "detect_junk",
        "1.0.0",
        "detect",
        provides=("junk_candidate",),
        score_weight=0.1,
        option_schema={
            "pack_id": {"type": "string", "default": "bt-advertisement-and-junk"},
            "extensions": {"type": "array", "items": {"type": "string"}},
            "filename_contains": {"type": "array", "items": {"type": "string"}},
            "protected_extensions": {"type": "array", "items": {"type": "string"}},
            "require_hash_evidence": {"type": "boolean", "default": False},
            "require_small_text": {"type": "boolean", "default": False},
        },
    )
    defaults = {".tmp", ".part", ".download", ".crdownload"}

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        from .junk_rules import DEFAULT_JUNK_PACK, evaluate_junk

        pack = DEFAULT_JUNK_PACK
        extensions = tuple(options.get("extensions", ()))
        keywords = tuple(options.get("filename_contains", ()))
        if extensions or keywords or options.get("protected_extensions"):
            from .junk_rules import JunkRule, JunkRulePack

            rules = list(pack.rules)
            if extensions:
                rules.insert(0, JunkRule("custom.extension", "Custom junk extension", "Configured junk extension.", "quarantine", 70, extensions=extensions))
            if keywords:
                rules.insert(0, JunkRule("custom.keyword", "Custom junk keyword", "Configured junk filename keyword.", "quarantine", 55, filename_contains=keywords))
            pack = JunkRulePack(
                pack.id,
                pack.version,
                pack.name,
                pack.description,
                tuple(rules),
                tuple(options.get("protected_extensions", pack.protected_extensions)),
            )
        evaluation = evaluate_junk(context, pack)
        if not evaluation.candidate:
            return ProcessorResult(status="skipped")
        evidence = [
            {"rule_id": item.rule_id, "action": item.action, "score": item.score, "reason": item.reason, "matched_value": item.matched_value}
            for item in evaluation.evidence
        ]
        return ProcessorResult(
            status="review" if evaluation.action == "review" else "matched",
            confidence_delta=min(0.5, evaluation.score / 100),
            fields={
                "junk_candidate": True,
                "junk_action": evaluation.action,
                "junk_score": evaluation.score,
                "junk_evidence": evidence,
            },
            reasons=[item.reason for item in evaluation.evidence],
        )


class DuplicateDetector(Processor):
    manifest = ProcessorManifest(
        "detect_duplicates",
        "1.0.0",
        "detect",
        provides=("duplicate_candidate", "duplicate_count"),
        score_weight=0.2,
        safety_class="review",
        option_schema={
            "method": {
                "type": "string",
                "enum": ["name_size", "normalized_name_size", "hash"],
                "default": "normalized_name_size",
            },
            "minimum_count": {"type": "integer", "default": 2},
        },
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        method = str(options.get("method", "normalized_name_size"))
        if method not in {"name_size", "normalized_name_size", "hash"}:
            return ProcessorResult(status="warning", warnings=["duplicate.method_invalid"])
        count = int(context.fields.get(f"{method}_duplicate_count", 0))
        minimum = max(2, int(options.get("minimum_count", 2)))
        if count < minimum:
            return ProcessorResult(status="skipped")
        return ProcessorResult(
            status="review",
            confidence_delta=self.manifest.score_weight,
            fields={
                "duplicate_candidate": True,
                "duplicate_count": count,
                "duplicate_method": method,
            },
            reasons=[f"duplicate.{method}_group_matched"],
            warnings=["duplicate.review_required"],
        )


class LanguageExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_language",
        "1.0.0",
        "extract",
        provides=("language",),
        score_weight=0.1,
        option_schema={"markers": {"type": "object"}},
    )
    default_markers = {
        "zh-CN": ["chs", "zh-cn", "sc"],
        "zh-TW": ["cht", "zh-tw", "tc"],
        "en": ["eng", "english"],
        "ja": ["jpn", "japanese"],
    }

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        stem = Path(context.original_name).stem.casefold()
        markers = options.get("markers", self.default_markers)
        for language, values in markers.items():
            if any(re.search(rf"(?<![a-z0-9]){re.escape(marker.casefold())}(?![a-z0-9])", stem) for marker in values):
                return ProcessorResult(
                    confidence_delta=0.1,
                    fields={"language": language},
                    reasons=["language.marker_matched"],
                )
        return ProcessorResult(status="skipped")


class SourcePrefixExtractor(Processor):
    manifest = ProcessorManifest(
        "extract_source_prefix",
        "1.0.0",
        "extract",
        provides=("source_prefix",),
        score_weight=0.05,
        option_schema={"prefixes": {"type": "array", "items": {"type": "string"}}},
    )

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        for prefix in options.get("prefixes", []):
            if context.original_name.casefold().startswith(str(prefix).casefold()):
                return ProcessorResult(
                    confidence_delta=0.05,
                    fields={"source_prefix": prefix},
                    reasons=["source_prefix.matched"],
                )
        return ProcessorResult(status="skipped")


class ClassificationProcessor(Processor):
    manifest = ProcessorManifest(
        "classify_extension",
        "1.0.0",
        "classify",
        provides=("category",),
        score_weight=0.1,
        option_schema={"categories": {"type": "object"}},
    )
    default_categories = {
        "video": [".mkv", ".mp4", ".avi", ".mov", ".webm"],
        "subtitle": [".srt", ".ass", ".ssa", ".vtt"],
        "image": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
        "archive": [".zip", ".7z", ".rar", ".tar", ".gz"],
        "document": [".pdf", ".txt", ".doc", ".docx"],
    }

    def process(self, context: ProcessingContext, options: dict[str, Any]) -> ProcessorResult:
        categories = options.get("categories", self.default_categories)
        for category, extensions in categories.items():
            if context.extension.casefold() in {str(value).casefold() for value in extensions}:
                return ProcessorResult(
                    confidence_delta=0.1,
                    fields={"category": category},
                    reasons=["classification.extension_matched"],
                )
        return ProcessorResult(status="skipped")


class ProcessorRegistry:
    def __init__(self) -> None:
        self._processors: dict[str, Processor] = {}

    def register(self, processor: Processor) -> None:
        if processor.manifest.id in self._processors:
            raise ValueError("processor.duplicate_id")
        self._processors[processor.manifest.id] = processor

    def get(self, processor_id: str) -> Processor:
        try:
            return self._processors[processor_id]
        except KeyError as exc:
            raise ValueError("processor.not_found") from exc

    def manifests(self) -> list[ProcessorManifest]:
        return [processor.manifest for processor in self._processors.values()]

    def validate_order(self, processor_ids: list[str]) -> None:
        available = {"filename", "relative_path", "parent_path", "extension", "size", "mtime_ns"}
        for processor_id in processor_ids:
            processor = self.get(processor_id)
            missing = set(processor.manifest.requires) - available
            if missing:
                raise ValueError(
                    f"processor.missing_dependencies:{processor_id}:{','.join(sorted(missing))}"
                )
            available.update(processor.manifest.provides)


def create_default_registry() -> ProcessorRegistry:
    registry = ProcessorRegistry()
    for processor in (
        DateExtractor(),
        IdentifierExtractor(),
        SequenceExtractor(),
        QualityExtractor(),
        ParentContextExtractor(),
        CustomRegexExtractor(),
        NameNormalizer(),
        TemplateTarget(),
        JunkDetector(),
        DuplicateDetector(),
        LanguageExtractor(),
        SourcePrefixExtractor(),
        ClassificationProcessor(),
    ):
        registry.register(processor)
    return registry
