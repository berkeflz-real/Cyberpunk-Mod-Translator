import hashlib
import json
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

VERSION = "1.0.3"
INPUT_FILE = "en-us.json"
OUTPUT_FILE = "tr-tr.json"
TERMINOLOGY_FILE = "terminology.json"
CHECKPOINT_FILE = "checkpoint.json"
MODEL_NAME = "gemini-3.5-flash-lite"
BATCH_SIZE = 50
MAX_RETRIES = 5
TARGET_LANGUAGE = "Turkish"
TARGET_CODE = "tr-tr"

REDSCRIPT_KEYS = {"category", "name", "desc", "title", "text", "label"}

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_input_file():
    for filename in (INPUT_FILE, "en-us.json.json"):
        if os.path.exists(filename):
            return filename
    return None


def detect_json_format(data):
    if (
        isinstance(data, dict)
        and isinstance(data.get("Data"), dict)
        and isinstance(data["Data"].get("RootChunk"), dict)
    ):
        return "archive"
    if isinstance(data, dict):
        return "flat"
    return "unknown"

# ---------------------------------------------------------------------------
# Entry extraction / apply
# ---------------------------------------------------------------------------
def extract_archive_entries(data):
    try:
        entries = data["Data"]["RootChunk"]["root"]["Data"]["entries"]
    except (KeyError, TypeError):
        return []

    result = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        female = entry.get("femaleVariant", "")
        male = entry.get("maleVariant", "")
        if not female and not male:
            continue
        result.append(
            {
                "index": index,
                "secondaryKey": entry.get("secondaryKey", ""),
                "female": female,
                "male": male,
            }
        )
    return result


def extract_flat_entries(data):
    result = []
    if not isinstance(data, dict):
        return result
    for index, (key, value) in enumerate(data.items()):
        if isinstance(value, str) and value.strip():
            result.append(
                {
                    "index": index,
                    "secondaryKey": str(key),
                    "female": value,
                    "male": "",
                }
            )
    return result


def create_batches(entries, batch_size=BATCH_SIZE):
    return [entries[i : i + batch_size] for i in range(0, len(entries), batch_size)]


def apply_archive_translations(data, batch, translations):
    entries = data["Data"]["RootChunk"]["root"]["Data"]["entries"]
    by_index = {item["index"]: item for item in translations}
    changed = 0
    for item in batch:
        translated = by_index[item["index"]]
        entry = entries[item["index"]]
        if entry.get("femaleVariant", ""):
            entry["femaleVariant"] = translated.get("female", entry.get("femaleVariant", ""))
        if entry.get("maleVariant", ""):
            entry["maleVariant"] = translated.get("male", entry.get("maleVariant", ""))
        changed += 1
    return changed


def apply_flat_translations(data, batch, translations):
    by_index = {item["index"]: item for item in translations}
    keys = list(data.keys())
    changed = 0
    for item in batch:
        key = keys[item["index"]]
        data[key] = by_index[item["index"]].get("female", data[key])
        changed += 1
    return changed

# ---------------------------------------------------------------------------
# Validation / protected tokens
# ---------------------------------------------------------------------------
def extract_special_tokens(text):
    if not text:
        return []
    patterns = [
        r"<[^>]+>",
        r"\{[^}]+\}",
        # Explicit %-delimited placeholders only. Normal percentages like 10%
        # or 75% are ordinary text and must never be treated as placeholders.
        r"%(?:[A-Za-z_][A-Za-z0-9_.:-]*|\d+)%",
        r"\\[nrt]",
        r"\[(?:/?[A-Za-z*][^\]]*)\]",
    ]
    tokens = []
    for pattern in patterns:
        tokens.extend(re.findall(pattern, text))
    return tokens


def _protect_special_tokens(text):
    """Replace protected formatting/placeholder tokens with inert sentinels before AI translation.

    This prevents the model from accidentally interpreting RichText/markup such as
    </>, <Rich ...>, {int_0}, BBCode tags, etc. as natural-language text and
    duplicating/removing them. The original tokens are restored after the API response.
    """
    if not text:
        return text, []

    tokens = extract_special_tokens(text)
    if not tokens:
        return text, []

    protected = text
    # Replace from left to right, but only the first occurrence of each extracted
    # token at each step. This preserves duplicate tokens as separate sentinels.
    for index, token in enumerate(tokens):
        sentinel = f"__CYTRANS_PROTECTED_{index:03d}__"
        protected = protected.replace(token, sentinel, 1)
    return protected, tokens


def _restore_special_tokens(text, tokens):
    """Restore protected tokens exactly once each and discard model-created duplicates.

    Gemini can occasionally repeat a protected sentinel even when the prompt asks it
    not to. Replacing every occurrence would turn those duplicates back into duplicate
    RichText/markup tags and make validation fail forever. Keep only the first occurrence
    of each expected sentinel. Missing sentinels are left for validation/retry because
    their exact placement cannot be inferred safely here.
    """
    if not text or not tokens:
        return text

    restored = text
    for index, token in enumerate(tokens):
        sentinel = f"__CYTRANS_PROTECTED_{index:03d}__"
        first = restored.find(sentinel)
        if first < 0:
            # Do not invent a position for a missing formatting token. The validator
            # will reject the entry and the selective recovery loop can retry it.
            continue

        second_start = first + len(sentinel)
        while True:
            duplicate = restored.find(sentinel, second_start)
            if duplicate < 0:
                break
            restored = restored[:duplicate] + restored[duplicate + len(sentinel):]
            second_start = duplicate

        restored = restored.replace(sentinel, token, 1)

    return restored


def _protect_batch_payload(batch):
    payload = []
    token_maps = {}
    for item in batch:
        female, female_tokens = _protect_special_tokens(item.get("female", ""))
        male, male_tokens = _protect_special_tokens(item.get("male", ""))
        token_maps[item["index"]] = {"female": female_tokens, "male": male_tokens}
        payload.append({
            "index": item["index"],
            "secondaryKey": item["secondaryKey"],
            "female": female,
            "male": male,
        })
    return payload, token_maps


def _restore_batch_translations(translations, token_maps):
    if not isinstance(translations, list):
        return translations
    for item in translations:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        mapping = token_maps.get(index)
        if not mapping:
            continue
        item["female"] = _restore_special_tokens(item.get("female", ""), mapping["female"])
        item["male"] = _restore_special_tokens(item.get("male", ""), mapping["male"])
    return translations


def _field_diagnostics(source, translated, label):
    errors = []
    if source and not translated:
        errors.append(f"{label} is empty while source is non-empty")
        return errors
    source_tokens = sorted(extract_special_tokens(source))
    target_tokens = sorted(extract_special_tokens(translated))
    if source_tokens != target_tokens:
        errors.append(
            f"{label} special-token mismatch; source={source_tokens!r}, target={target_tokens!r}"
        )
    return errors


def validate_special_tokens(source, translated):
    return not _field_diagnostics(source, translated, "translation")


def validate_translation_fields(source, translated):
    return not _field_diagnostics(source, translated, "translation")


def diagnose_translation_failures(batch, translations):
    expected = {item["index"]: item for item in batch}
    counts = {}
    for item in translations:
        if isinstance(item, dict):
            counts[item.get("index")] = counts.get(item.get("index"), 0) + 1

    failures = {}
    for index in expected:
        if counts.get(index, 0) == 0:
            failures[index] = ["Missing translation"]
        elif counts.get(index, 0) > 1:
            failures[index] = ["Duplicate translation index"]

    for item in translations:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if index not in expected or counts.get(index, 0) != 1:
            continue

        source = expected[index]
        errors = []
        if item.get("secondaryKey", "") != source.get("secondaryKey", ""):
            errors.append("secondaryKey mismatch")

        errors.extend(
            _field_diagnostics(
                source.get("female", ""),
                item.get("female", ""),
                "Female",
            )
        )

        source_male = source.get("male", "")
        target_male = item.get("male", "")
        if not source_male and target_male:
            errors.append("Male field unexpectedly populated")
        elif source_male:
            errors.extend(_field_diagnostics(source_male, target_male, "Male"))

        if errors:
            failures[index] = errors

    return failures


def validate_translations(batch, translations):
    failures = diagnose_translation_failures(batch, translations)
    errors = []
    for index, reasons in failures.items():
        for reason in reasons:
            errors.append(f"index {index}: {reason}")

    expected = {item["index"] for item in batch}
    received = {
        item.get("index") for item in translations if isinstance(item, dict)
    }
    extra = received - expected
    if extra:
        errors.append(f"Unexpected indices: {sorted(extra)}")

    return {
        "has_error": bool(errors),
        "errors": errors,
        "missing_indices": expected - received,
        "extra_indices": extra,
    }

# ---------------------------------------------------------------------------
# Terminology / checkpoints
# ---------------------------------------------------------------------------
def _load_raw_terminology():
    if not os.path.exists(TERMINOLOGY_FILE):
        return {}
    try:
        return load_json(TERMINOLOGY_FILE)
    except Exception:
        return {}


def load_terminology():
    raw = _load_raw_terminology()
    if isinstance(raw, dict) and isinstance(raw.get("languages"), dict):
        value = raw["languages"].get(TARGET_LANGUAGE, {})
        return dict(value) if isinstance(value, dict) else {}
    return dict(raw) if isinstance(raw, dict) else {}


def save_terminology(terminology):
    raw = _load_raw_terminology()
    if not isinstance(raw, dict) or not isinstance(raw.get("languages"), dict):
        raw = {"languages": {}}
    raw["languages"][TARGET_LANGUAGE] = dict(terminology)
    save_json(TERMINOLOGY_FILE, raw)


def merge_terminology(terminology, new_terms):
    for item in new_terms or []:
        if not isinstance(item, dict):
            continue
        english = str(item.get("english", "")).strip()
        translation = str(
            item.get("translation", item.get("target", item.get("turkish", "")))
        ).strip()
        if english and translation and english not in terminology:
            terminology[english] = translation
    return terminology


def _fingerprint(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return {
        "input": os.path.abspath(path),
        "sha256": hasher.hexdigest(),
        "target_code": TARGET_CODE,
    }


def load_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return {"completed_batches": []}
    try:
        value = load_json(CHECKPOINT_FILE)
        return value if isinstance(value, dict) else {"completed_batches": []}
    except Exception:
        return {"completed_batches": []}


def save_checkpoint(completed_batches, metadata=None):
    payload = {"completed_batches": sorted(set(completed_batches))}
    if metadata is not None:
        payload["metadata"] = metadata
    save_json(CHECKPOINT_FILE, payload)

# ---------------------------------------------------------------------------
# Gemini / retries
# ---------------------------------------------------------------------------
def _transient_api_error(error):
    text = str(error).upper()
    return any(
        marker in text
        for marker in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")
    )


def _backoff_seconds(attempt):
    return min(30, 2 ** max(0, attempt - 1))


def translate_batch(client, batch, terminology, validation_feedback=None):
    payload, token_maps = _protect_batch_payload(batch)

    feedback = validation_feedback or "None"
    prompt = f"""
You are a professional Cyberpunk 2077 mod localization translator.
Translate English user-visible text into {TARGET_LANGUAGE}.

STRICT RULES:
1. Return every supplied index exactly once.
2. Never change index.
3. Never change secondaryKey.
4. Translate only female and male.
5. If source male is empty, target male must stay empty.
6. Translate ordinary UI labels naturally.
7. Preserve proper nouns and established Cyberpunk terminology where natural.
8. Preserve ALL placeholders, tags, variables, escape sequences, and BBCode. Protected tokens
   are represented as __CYTRANS_PROTECTED_NNN__ sentinels; copy each sentinel exactly once and
   never translate, duplicate, delete, reorder, or otherwise modify a sentinel.
9. Do not translate code/technical identifiers inside protected syntax.
10. Never change internal identifiers.
11. Use natural, idiomatic {TARGET_LANGUAGE}.
12. Use native Unicode for the target language; never transliterate into ASCII.
13. For Turkish, preserve ğ Ğ ı İ ö Ö ş Ş ü Ü when applicable.
14. Normal percentages such as 10% and 75% are ordinary text, not placeholders.

VALIDATION RECOVERY FEEDBACK:
{feedback}

TERMINOLOGY:
{json.dumps(terminology, ensure_ascii=False, indent=2)}

ENTRIES:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY JSON in this schema. If no new terminology is needed, return an empty newTerminology array:
{{
  "translations": [
    {{
      "index": 0,
      "secondaryKey": "...",
      "female": "...",
      "male": "..."
    }}
  ],
  "newTerminology": [
    {{
      "english": "...",
      "translation": "..."
    }}
  ]
}}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.25,
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "translations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "secondaryKey": {"type": "string"},
                                "female": {"type": "string"},
                                "male": {"type": "string"},
                            },
                            "required": [
                                "index",
                                "secondaryKey",
                                "female",
                                "male",
                            ],
                        },
                    },
                    "newTerminology": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "english": {"type": "string"},
                                "translation": {"type": "string"},
                            },
                            "required": ["english", "translation"],
                        },
                    },
                },
                "required": ["translations", "newTerminology"],
            },
        ),
    )
    result = json.loads(response.text)
    result["translations"] = _restore_batch_translations(
        result.get("translations", []),
        token_maps,
    )
    return result


def _build_recovery_feedback(failures, batch, translations):
    source_by_index = {item["index"]: item for item in batch}
    previous_by_index = {
        item.get("index"): item
        for item in translations
        if isinstance(item, dict)
    }
    lines = [
        "Validation failed for these specific entries. Correct ONLY those entries.",
        "Preserve every placeholder, tag, escape sequence, percentage, and secondaryKey exactly.",
    ]
    for index in sorted(failures):
        source = source_by_index[index]
        lines.append(f"INDEX {index}: {'; '.join(failures[index])}")
        lines.append(f"SOURCE FEMALE: {source.get('female', '')[:1000]}")
        previous = previous_by_index.get(index)
        if previous and previous.get("female"):
            lines.append(f"PREVIOUS FEMALE: {previous.get('female', '')[:1000]}")
        if source.get("male"):
            lines.append(f"SOURCE MALE: {source.get('male', '')[:1000]}")
    return "\n".join(lines)


def translate_batch_with_recovery(
    client,
    batch,
    terminology,
    log_func=None,
    label="batch",
):
    remaining = list(batch)
    current_terms = dict(terminology or {})
    collected = {}
    feedback = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if log_func:
                if feedback:
                    log_func(
                        f"-> Validation recovery round {attempt}/{MAX_RETRIES}: "
                        f"retrying {len(remaining)} failed entrie(s) for {label}."
                    )
                else:
                    log_func(
                        f"-> Translation request round {attempt}/{MAX_RETRIES} for {label}..."
                    )

            result = translate_batch(
                client,
                remaining,
                current_terms,
                validation_feedback=feedback,
            )
            translations = result.get("translations", [])
            if log_func:
                log_func(
                    f"-> Translations received: {len(translations)} for {label}."
                )

            current_terms = merge_terminology(
                current_terms,
                result.get("newTerminology", []),
            )
            failures = diagnose_translation_failures(remaining, translations)
            remaining_indexes = {item["index"] for item in remaining}
            counts = {}
            for item in translations:
                if isinstance(item, dict):
                    counts[item.get("index")] = counts.get(item.get("index"), 0) + 1

            for item in translations:
                if not isinstance(item, dict):
                    continue
                index = item.get("index")
                if (
                    index in remaining_indexes
                    and counts.get(index) == 1
                    and index not in failures
                ):
                    collected[index] = item

            if not failures:
                ordered = [collected[item["index"]] for item in batch]
                return {"translations": ordered, "terminology": current_terms}

            if log_func:
                for index in sorted(failures):
                    log_func(
                        f"-> Validation detail at index {index}: "
                        + " | ".join(failures[index])
                    )
                good = len(remaining) - len(failures)
                if good:
                    log_func(
                        f"-> Keeping {good} valid result(s); only "
                        f"{len(failures)} failed entrie(s) will be retried."
                    )

            remaining = [
                item for item in remaining if item["index"] in failures
            ]
            feedback = _build_recovery_feedback(failures, remaining, translations)

            if attempt < MAX_RETRIES:
                delay = _backoff_seconds(attempt)
                if log_func:
                    log_func(
                        f"-> Validation retry backoff: {delay}s before retry {attempt + 1}/{MAX_RETRIES}."
                    )
                time.sleep(delay)

        except Exception as error:
            if _transient_api_error(error) and attempt < MAX_RETRIES:
                delay = _backoff_seconds(attempt)
                if log_func:
                    log_func(
                        f"-> Gemini temporarily unavailable; retrying in {delay}s "
                        f"({attempt + 1}/{MAX_RETRIES})..."
                    )
                time.sleep(delay)
                continue

            if attempt >= MAX_RETRIES:
                raise

            delay = _backoff_seconds(attempt)
            if log_func:
                log_func(f"-> Translation round retry in {delay}s: {error}")
            time.sleep(delay)

    raise RuntimeError(f"{label} failed after {MAX_RETRIES} recovery rounds.")

# ---------------------------------------------------------------------------
# Codeware localization
# ---------------------------------------------------------------------------
CODEWARE_PACKAGE_RE = re.compile(
    r"(public\s+class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s+extends\s+ModLocalizationPackage\b)",
    re.MULTILINE,
)
CODEWARE_TEXT_RE = re.compile(
    r'(this\.Text\(\s*")((?:[^"\\]|\\.)*)("\s*,\s*")((?:[^"\\]|\\.)*)(")',
    re.MULTILINE,
)
CODEWARE_PROVIDER_RE = re.compile(r"extends\s+ModLocalizationProvider\b", re.MULTILINE)


def is_codeware_package_file(filepath):
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return False
    return CODEWARE_PACKAGE_RE.search(content) is not None and "this.Text(" in content


def is_codeware_provider_file(filepath):
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return False
    return CODEWARE_PROVIDER_RE.search(content) is not None and "GetPackage" in content


def get_codeware_package_class(content):
    match = CODEWARE_PACKAGE_RE.search(content)
    return match.group(2) if match else None


def codeware_class_name_for_target(target_language):
    words = re.findall(r"[A-Za-z0-9]+", target_language)
    return "".join(word[:1].upper() + word[1:] for word in words) or "Translated"


def extract_codeware_entries(content):
    return [
        {
            "index": index,
            "secondaryKey": match.group(2),
            "female": match.group(4),
            "male": "",
            "value_start": match.start(4),
            "value_end": match.end(4),
        }
        for index, match in enumerate(CODEWARE_TEXT_RE.finditer(content))
    ]


def translate_codeware_package(
    client,
    filepath,
    output_filepath,
    terminology,
    target_class_name="English",
    log_func=None,
):
    source_content = Path(filepath).read_text(encoding="utf-8")
    entries = extract_codeware_entries(source_content)
    if not entries:
        if log_func:
            log_func("Codeware package detected but contains no translatable entries.")
        return False

    translations_by_index = {}
    current_terms = dict(terminology or {})
    batches = create_batches(entries)
    for batch_number, batch in enumerate(batches, 1):
        recovery = translate_batch_with_recovery(
            client,
            batch,
            current_terms,
            log_func=log_func,
            label=f"Codeware localization batch {batch_number}/{len(batches)}",
        )
        current_terms = recovery["terminology"]
        for item in recovery["translations"]:
            translations_by_index[item["index"]] = item
        save_terminology(current_terms)

    translated_content = source_content
    for entry in reversed(entries):
        translation = translations_by_index.get(entry["index"])
        if translation is None:
            raise RuntimeError(
                f"Missing Codeware translation for {entry['secondaryKey']}"
            )
        source = entry["female"]
        target = translation.get("female", source)
        if not validate_translation_fields(source, target):
            raise RuntimeError(
                f"Invalid Codeware translation for {entry['secondaryKey']}"
            )
        translated_content = (
            translated_content[: entry["value_start"]]
            + target
            + translated_content[entry["value_end"] :]
        )

    # Keep the class named English. The provider's existing en-us fallback can
    # therefore serve the translated text without modifying provider code.
    Path(output_filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(output_filepath).write_text(translated_content, encoding="utf-8")
    return True


def update_codeware_provider(provider_filepath, target_code, target_class_name):
    # Retained for compatibility with earlier releases. v1.0.3 intentionally
    # does not patch providers for the fallback-compatible in-place strategy.
    return False

# ---------------------------------------------------------------------------
# Redscript Config / BBCode TXT
# ---------------------------------------------------------------------------
def extract_redscript_config_values(data, output):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in REDSCRIPT_KEYS and isinstance(value, str) and len(value.strip()) > 1:
                output.add(value)
            else:
                extract_redscript_config_values(value, output)
    elif isinstance(data, list):
        for value in data:
            extract_redscript_config_values(value, output)


def translate_redscript_config_file(client, filepath, terminology, log_func=None):
    try:
        data = load_json(filepath)
    except Exception:
        return False
    values = set()
    extract_redscript_config_values(data, values)
    strings = list(values)
    if not strings:
        return False

    batch = [
        {"index": i, "secondaryKey": text, "female": text, "male": ""}
        for i, text in enumerate(strings)
    ]
    recovery = translate_batch_with_recovery(
        client,
        batch,
        terminology,
        log_func=log_func,
        label=f"RedscriptConfig {Path(filepath).name}",
    )
    by_index = {item["index"]: item for item in recovery["translations"]}

    def replace_values(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in REDSCRIPT_KEYS and isinstance(child, str) and child in strings:
                    value[key] = by_index[strings.index(child)].get("female", child)
                else:
                    replace_values(child)
        elif isinstance(value, list):
            for child in value:
                replace_values(child)

    replace_values(data)
    save_json(filepath, data)
    return True


def translate_bbcode_txt_file(client, filepath, terminology, log_func=None):
    content = Path(filepath).read_text(encoding="utf-8")
    paragraphs = list(
        dict.fromkeys(
            [
                paragraph.strip()
                for paragraph in content.split("\n\n")
                if paragraph.strip() and re.search(r"[A-Za-z]", paragraph)
            ]
        )
    )
    if not paragraphs:
        return False

    batch = [
        {"index": i, "secondaryKey": p, "female": p, "male": ""}
        for i, p in enumerate(paragraphs)
    ]
    recovery = translate_batch_with_recovery(
        client,
        batch,
        terminology,
        log_func=log_func,
        label=f"BBCode TXT {Path(filepath).name}",
    )
    by_index = {item["index"]: item for item in recovery["translations"]}
    for i, paragraph in enumerate(paragraphs):
        content = content.replace(paragraph, by_index[i].get("female", paragraph))
    Path(filepath).write_text(content, encoding="utf-8")
    return True

# ---------------------------------------------------------------------------
# Selective Lua localization
# ---------------------------------------------------------------------------
LUA_KEY_RE = re.compile(
    r'(?P<prefix>\b(?:title|description|label|tooltip|displayName|settingName|categoryName|text|header|help|message)\s*=\s*")'
    r'(?P<value>(?:[^"\\]|\\.)*)(?P<suffix>")',
    re.IGNORECASE,
)
LUA_CALL_RE = re.compile(
    r'(?P<prefix>\b(?:localize|getText|gettext|tr|translateText)\s*\(\s*")'
    r'(?P<value>(?:[^"\\]|\\.)*)(?P<suffix>")',
    re.IGNORECASE,
)


def _lua_candidates(content):
    matches = []
    for regex in (LUA_KEY_RE, LUA_CALL_RE):
        matches.extend(regex.finditer(content))
    matches.sort(key=lambda match: match.start())
    unique = []
    seen = set()
    for match in matches:
        if match.start() not in seen:
            unique.append(match)
            seen.add(match.start())
    return unique


def is_lua_localization_file(filepath):
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return False
    lower = content.lower()
    name = Path(filepath).name.lower()
    candidates = _lua_candidates(content)
    if not candidates:
        return False
    if any(
        marker in name
        for marker in ("settings", "localization", "locale", "loc", "ui", "menu", "config")
    ):
        return True
    return any(
        marker in lower
        for marker in (
            "nativesettings",
            "modsettings",
            "registersetting",
            "registerinput",
            "settings",
            "localize(",
            "gettext(",
            "tooltip",
            "displayname",
        )
    )


def translate_lua_localization_file(client, filepath, terminology, log_func=None):
    path = Path(filepath)
    content = path.read_text(encoding="utf-8")
    matches = _lua_candidates(content)
    entries = []
    for match_index, match in enumerate(matches):
        value = match.group("value")
        if len(value.strip()) < 2 or not re.search(r"[A-Za-z]", value):
            continue
        entries.append(
            {
                "index": match_index,
                "secondaryKey": value,
                "female": value,
                "male": "",
                "start": match.start("value"),
                "end": match.end("value"),
            }
        )
    if not entries:
        return False

    recovery = translate_batch_with_recovery(
        client,
        entries,
        terminology,
        log_func=log_func,
        label=f"Lua {path.name}",
    )
    by_index = {item["index"]: item for item in recovery["translations"]}
    replacements = []
    for entry in entries:
        target = by_index[entry["index"]].get("female", entry["female"])
        if not validate_translation_fields(entry["female"], target):
            raise RuntimeError(f"Invalid Lua translation at index {entry['index']}")
        escaped = json.dumps(target, ensure_ascii=False)[1:-1]
        replacements.append((entry["start"], entry["end"], escaped))

    for start, end, replacement in reversed(replacements):
        content = content[:start] + replacement + content[end:]
    path.write_text(content, encoding="utf-8")
    return True

# ---------------------------------------------------------------------------
# Main translator entry point
# ---------------------------------------------------------------------------
def main():
    actual_input = find_input_file()
    if not actual_input:
        raise FileNotFoundError("Source JSON file not found.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)
    output_exists = os.path.exists(OUTPUT_FILE)
    data = load_json(OUTPUT_FILE) if output_exists else load_json(actual_input)
    mode = detect_json_format(data)
    if mode == "archive":
        entries = extract_archive_entries(data)
    elif mode == "flat":
        entries = extract_flat_entries(data)
    else:
        raise ValueError("Unsupported JSON format.")

    if not entries:
        save_json(OUTPUT_FILE, data)
        print("No translatable entries found.")
        return

    print("============================================================")
    print("CYBERPUNK 2077 AI TRANSLATOR")
    print("============================================================")
    print(f"Target language: {TARGET_LANGUAGE}")
    print(f"Entries: {len(entries)}")
    print(f"Batch size: {BATCH_SIZE}")

    batches = create_batches(entries)
    metadata = _fingerprint(actual_input)
    checkpoint = load_checkpoint()
    checkpoint_valid = (
        output_exists and checkpoint.get("metadata") == metadata
    )
    completed = (
        set(checkpoint.get("completed_batches", [])) if checkpoint_valid else set()
    )
    print(f"Completed batches: {len(completed)}/{len(batches)}")

    if completed and len(completed) < len(batches):
        first_incomplete = next(
            index for index in range(len(batches)) if index not in completed
        )
        print(
            f"Resuming from batch {first_incomplete + 1}/{len(batches)}"
        )

    terminology = load_terminology()
    for batch_index, batch in enumerate(batches):
        if batch_index in completed:
            print(
                f"BATCH {batch_index + 1}/{len(batches)} already completed, skipping."
            )
            continue

        print(f"BATCH {batch_index + 1}/{len(batches)}")
        recovery = translate_batch_with_recovery(
            client,
            batch,
            terminology,
            log_func=print,
            label=f"archive batch {batch_index + 1}/{len(batches)}",
        )
        translations = recovery["translations"]
        terminology = recovery["terminology"]

        if mode == "archive":
            changed = apply_archive_translations(data, batch, translations)
        else:
            changed = apply_flat_translations(data, batch, translations)

        if changed != len(batch):
            raise RuntimeError(
                f"Applied {changed}/{len(batch)} entries instead of {len(batch)}."
            )

        save_terminology(terminology)
        save_json(OUTPUT_FILE, data)
        completed.add(batch_index)
        save_checkpoint(completed, metadata)
        print("✓ BATCH COMPLETED")

    print("============================================================")
    print("TRANSLATION COMPLETED")
    print("============================================================")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Completed batches: {len(completed)}/{len(batches)}")


if __name__ == "__main__":
    main()
