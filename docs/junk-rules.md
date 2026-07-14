# Junk and Advertisement Rules

File Curator uses deterministic metadata evidence to identify candidates. The default `bt-advertisement-and-junk` pack checks incomplete-download extensions, link files, promotion keywords, domain patterns, empty files, small text/HTML attachments, unusually small media, and sample/trailer markers.

Each match records the rule ID, matched value, score, reason, and suggested action. Scores are explainable rule totals rather than AI probabilities. A candidate can remain in place for review or be proposed for `.file-curator-quarantine`; no rule permanently deletes a file.

Protected sidecars currently include `.srt`, `.ass`, `.ssa`, and `.nfo`. Generic rules do not flag these extensions. A small file alone is never enough for automatic deletion, and all quarantine operations still require plan review, freeze, and confirmation.

The built-in pack is available from `GET /api/junk-rule-packs`. Use `POST /api/junk-rule-packs/validate` to validate a custom JSON pack. The desktop **Junk rules** page shows every built-in rule and exposes the validation editor.

The current phase reads indexed metadata only. Repeated-hash evidence and opt-in inspection of small text/link files are planned extensions and will reuse the same evidence model.
