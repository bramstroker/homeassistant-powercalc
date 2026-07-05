---
name: powercalc-translations
description: Use when adding, removing, renaming, or changing PowerCalc Home Assistant translation keys or strings; en.json is the source, all locale files must keep matching keys and placeholders.
---

# SKILL: PowerCalc Translations

## Skill ID
powercalc.translations

## Description
Use this skill whenever a task adds, removes, renames, or changes translation keys or translated strings for PowerCalc.

## When This Skill Should Be Used

Use this skill for changes under:

```
custom_components/powercalc/translations/*.json
```

Also use it when implementation work adds or changes UI text, config flow strings, repair strings, selector labels, common strings, or any Home Assistant translation key consumed by PowerCalc.

## Source of Truth

- `custom_components/powercalc/translations/en.json` is always the source translation file.
- Every other translation file must contain the same nested key paths as `en.json`.
- Non-English files must not introduce extra keys that are absent from `en.json`.
- Preserve the structure and key order from `en.json` when adding missing keys.

## Translation Mode Question

Before modifying non-English translation files, ask the user one concise question unless the task already answers it:

```
Should I copy the English strings into the other locale files, or should I actually translate them?
```

If the user chooses copy mode, copy the exact English string for new or changed keys into every locale.
If the user chooses translate mode, translate the human-readable text while preserving every placeholder exactly.

## Placeholder Rules

Placeholders use Home Assistant style braces, for example `{entity}`, `{source}`, or `{docs_uri}`.

For every string path that exists in `en.json`:

- Every locale must contain the exact same placeholder names for that path.
- Do not translate placeholder names.
- Do not add, remove, rename, or reorder placeholder braces while translating.
- If an English string changes placeholders, update every locale string at that same path.

## Workflow

1. Read `custom_components/powercalc/translations/en.json` first.
2. Make the intended translation change in `en.json`.
3. Apply the same key structure change to every other `*.json` file in `custom_components/powercalc/translations/`.
4. Use the chosen translation mode for non-English values.
5. Preserve valid JSON formatting and existing indentation.
6. Verify key parity and placeholders before claiming completion.

## Validation

Before running tests, compare the nested leaf key paths in every locale file against `en.json`. Missing or extra paths must be fixed against `en.json`.

Run:

```
python .github/scripts/validate_translations.py
uv run pytest tests/test_translations.py
```

The validation script and test must pass before the work is complete.

## Guardrails

- Do not edit translation keys in only one locale.
- Do not delete locale keys unless the same key was removed from `en.json`.
- Do not rely on machine translation when the user requested copy mode.
- Do not claim translated language accuracy unless it was reviewed or the user explicitly requested best-effort translation.
