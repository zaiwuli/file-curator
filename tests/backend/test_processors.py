from file_curator.processors import (
    DateExtractor,
    IdentifierExtractor,
    NameNormalizer,
    ProcessingContext,
    SequenceExtractor,
    TemplateTarget,
)


def context(name: str) -> ProcessingContext:
    return ProcessingContext(
        entry_id="1",
        relative_path=name,
        original_name=name,
        parent_path="",
        extension=".mp4",
        size=1,
        mtime_ns=1,
    )


def test_extractors_return_explainable_fields() -> None:
    item = context("2026-05-18 ABC-123 (2).mp4")
    date_result = DateExtractor().process(item, {})
    identifier_result = IdentifierExtractor().process(item, {})
    sequence_result = SequenceExtractor().process(item, {})
    assert date_result.fields["date"] == "2026-05-18"
    assert identifier_result.fields["identifier"] == "ABC-123"
    assert sequence_result.fields["sequence"] == 2
    assert date_result.reasons == ["date.full_date_matched"]


def test_invalid_calendar_date_is_warning() -> None:
    result = DateExtractor().process(context("2026-02-31 item.mp4"), {})
    assert result.status == "warning"
    assert result.warnings == ["date.invalid"]


def test_date_extractor_accepts_chinese_separators() -> None:
    result = DateExtractor().process(context("archive-2024\u5e741\u670831\u65e5.mp4"), {})
    assert result.fields["date"] == "2024-01-31"


def test_normalizer_preserves_identifier_and_extension() -> None:
    result = NameNormalizer().process(
        context("www.site@ABC-123   title.MP4"), {"remove_prefixes": ["www.site@"]}
    )
    assert result.proposed_name == "ABC-123 title.mp4"


def test_template_missing_field_requires_review() -> None:
    result = TemplateTarget().process(context("name.mp4"), {"parent_template": "{year}"})
    assert result.status == "review"
    assert result.warnings == ["template.missing_field:year"]
