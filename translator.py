import json
import os
import re
import time

from google import genai
from google.genai import types

# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "en-us.json"
OUTPUT_FILE = "tr-tr.json"
TERMINOLOGY_FILE = "terminology.json"
CHECKPOINT_FILE = "checkpoint.json"

MODEL_NAME = "gemini-3.5-flash-lite"
BATCH_SIZE = 50
MAX_RETRIES = 5

# Set by app.py before main() is called.
TARGET_LANGUAGE = "Turkish"
TARGET_CODE = "tr-tr"

COMMON_UI_WORDS = {
    "settings", "setting", "enable", "disable", "enabled", "disabled",
    "save", "cancel", "close", "open", "back", "next", "previous",
    "continue", "confirm", "apply", "delete", "remove", "yes", "no",
    "on", "off", "general", "options", "controls", "inventory",
    "phone", "messages", "message", "new", "loading", "done", "start",
    "stop", "reset", "default", "description", "speed", "movement",
}

REDSCRIPT_KEYS = {"category", "name", "desc", "title", "text", "label"}

# ============================================================
# JSON / FILE HELPERS
# ============================================================

def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_input_file():
    for filename in (INPUT_FILE, "en-us.json.json"):
        if os.path.exists(filename):
            return filename
    return None

def detect_json_format(data):
    if not isinstance(data, dict):
        return "unknown"
    if isinstance(data.get("Data"), dict) and isinstance(data["Data"].get("RootChunk"), dict):
        return "archive"
    return "flat"

# ============================================================
# ENTRY EXTRACTION
# ============================================================

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
        secondary_key = entry.get("secondaryKey", "")
        
        if not female and not male:
            continue
            
        result.append({
            "index": index, 
            "secondaryKey": secondary_key, 
            "female": female, 
            "male": male
        })
    return result

def extract_flat_entries(data):
    result = []
    index = 0
    if not isinstance(data, dict):
        return result
        
    for key, value in data.items():
        if isinstance(value, str) and value.strip():
            result.append({
                "index": index, 
                "secondaryKey": key, 
                "female": value, 
                "male": ""
            })
            index += 1
    return result

def create_batches(entries, batch_size):
    return [entries[i:i + batch_size] for i in range(0, len(entries), batch_size)]

# ============================================================
# PLACEHOLDERS / TAGS
# ============================================================

def extract_special_tokens(text):
    if not text:
        return []
    patterns = [r"<[^>]+>", r"\{[^}]+\}", r"%[^%]+%", r"\\[nrt]"]
    tokens = []
    for pattern in patterns:
        tokens.extend(re.findall(pattern, text))
    return tokens

def validate_special_tokens(source, translated):
    return sorted(extract_special_tokens(source)) == sorted(extract_special_tokens(translated))

def validate_translation_fields(source, translated):
    if source and not translated:
        return False
    return validate_special_tokens(source, translated)

def validate_translations(batch, translations):
    expected_set = {item["index"] for item in batch}
    received_set = {item.get("index") for item in translations}
    
    errors = []
    missing = expected_set - received_set
    extra = received_set - expected_set
    duplicate = {i for i in set(item.get("index") for item in translations) if [t.get("index") for t in translations].count(i) > 1}
    
    if missing:
        errors.append(f"Missing indices: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected indices: {sorted(extra)}")
    if duplicate:
        errors.append(f"Duplicate indices: {sorted(duplicate)}")

    original_by_index = {item["index"]: item for item in batch}
    for item in translations:
        index = item.get("index")
        if index not in original_by_index:
            continue
            
        source = original_by_index[index]
        if item.get("secondaryKey", "") != source["secondaryKey"]:
            errors.append(f"secondaryKey mismatch at index {index}")
            
        if not validate_translation_fields(source.get("female", ""), item.get("female", "")):
            errors.append(f"Female translation validation failed at index {index}")
            
        source_male = source.get("male", "")
        target_male = item.get("male", "")
        
        if not source_male and target_male:
            errors.append(f"Male field unexpectedly populated at index {index}")
        elif source_male and not validate_translation_fields(source_male, target_male):
            errors.append(f"Male translation validation failed at index {index}")

    return {
        "has_error": bool(errors), 
        "errors": errors, 
        "missing_indices": missing, 
        "extra_indices": extra, 
        "duplicate_indices": duplicate
    }

# ============================================================
# TERMINOLOGY & CHECKPOINT
# ============================================================

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
        bucket = raw["languages"].get(TARGET_LANGUAGE, {})
        return dict(bucket) if isinstance(bucket, dict) else {}
        
    if TARGET_CODE == "tr-tr" and isinstance(raw, dict) and all(isinstance(v, str) for v in raw.values()):
        return dict(raw)
    return {}

def save_terminology(terminology):
    raw = _load_raw_terminology()
    if not isinstance(raw, dict) or not isinstance(raw.get("languages"), dict):
        old_flat = raw if isinstance(raw, dict) else {}
        raw = {"languages": {}}
        if TARGET_CODE == "tr-tr" and old_flat and all(isinstance(v, str) for v in old_flat.values()):
            raw["languages"]["Turkish"] = old_flat
            
    raw["languages"][TARGET_LANGUAGE] = terminology
    save_json(TERMINOLOGY_FILE, raw)

def merge_terminology(terminology, new_terms):
    if not isinstance(new_terms, list):
        return terminology
        
    for item in new_terms:
        if not isinstance(item, dict):
            continue
        english = str(item.get("english", "")).strip()
        translation = str(item.get("translation", item.get("target", item.get("turkish", "")))).strip()
        
        if english and translation and english not in terminology:
            terminology[english] = translation
    return terminology

def load_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return {"completed_batches": []}
    try:
        value = load_json(CHECKPOINT_FILE)
        if isinstance(value, dict):
            value.setdefault("completed_batches", [])
            return value
    except Exception:
        pass
    return {"completed_batches": []}

def save_checkpoint(completed_batches):
    save_json(CHECKPOINT_FILE, {"completed_batches": sorted(completed_batches)})

# ============================================================
# GEMINI
# ============================================================

def translate_batch(client, batch, terminology):
    payload = [
        {
            "index": item["index"],
            "female": item["female"],
            "male": item["male"]
        } for item in batch
    ]
    
    prompt = f"""
You are a professional Cyberpunk 2077 mod localization translator.
Translate English user-visible text into {TARGET_LANGUAGE}.

STRICT RULES:
1. Return every supplied index exactly once.
2. Never change index.
3. Return only translation fields; do not invent or modify internal metadata.
4. Translate only female and male.
5. If source male is empty, target male must stay empty.
6. Ordinary UI labels must not remain in English. Examples: Settings, Enable, Disable, Save, Cancel, Continue, Close, General, Speed.
7. Preserve proper nouns and established Cyberpunk terminology where natural.
8. Preserve ALL placeholders, tags, variables, escape sequences, and BBCode (like [b], [color=...], [list], [*], [i]).
9. DO NOT translate any code or technical text inside [code]...[/code] blocks.
10. Use natural, idiomatic {TARGET_LANGUAGE}, not literal English word order.
11. If a source sentence is ordinary user-visible text, do not simply repeat the English source unchanged.

TERMINOLOGY FOR {TARGET_LANGUAGE}:
{json.dumps(terminology, ensure_ascii=False, indent=2)}

ENTRIES:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY JSON in this schema:
{{
  "translations": [
    {{
      "index": 0,
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
                                "female": {"type": "string"},
                                "male": {"type": "string"},
                            },
                            "required": ["index", "female", "male"],
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

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    result = json.loads(response.text)

    # secondaryKey is immutable source metadata. It is keyed by index and
    # must never depend on model output. Reattach it from the original batch
    # before validation/application so a model typo cannot invalidate an
    # otherwise correct translation batch.
    original_by_index = {item["index"]: item for item in batch}
    for item in result.get("translations", []):
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        source = original_by_index.get(index)
        if source is not None:
            item["secondaryKey"] = source["secondaryKey"]

    return result

# ============================================================
# APPLY TRANSLATIONS
# ============================================================

def apply_archive_translations(data, batch, translations):
    entries = data.get("Data", {}).get("RootChunk", {}).get("root", {}).get("Data", {}).get("entries", [])
    by_index = {item["index"]: item for item in translations}
    changed = 0
    
    for original in batch:
        index = original["index"]
        translation = by_index.get(index)
        
        if translation is None:
            raise RuntimeError(f"Missing translation for index {index}.")
        if index >= len(entries):
            raise RuntimeError(f"Invalid entry index {index}.")
            
        entry = entries[index]
        if entry.get("secondaryKey", "") != translation.get("secondaryKey", ""):
            raise RuntimeError(f"secondaryKey mismatch at index {index}.")
        
        if "femaleVariant" in entry:
            source = entry.get("femaleVariant", "")
            target = translation.get("female", "")
            if not validate_translation_fields(source, target):
                raise RuntimeError(f"Female translation validation failed at index {index}.")
            entry["femaleVariant"] = target
            
        if "maleVariant" in entry:
            source = entry.get("maleVariant", "")
            target = translation.get("male", "")
            if source:
                if not validate_translation_fields(source, target):
                    raise RuntimeError(f"Male translation validation failed at index {index}.")
                entry["maleVariant"] = target
            elif target:
                raise RuntimeError(f"Male unexpectedly populated at index {index}.")
        changed += 1
        
    return changed

def apply_flat_translations(data, batch, translations):
    by_index = {item["index"]: item for item in translations}
    changed = 0
    
    for original in batch:
        translation = by_index[original["index"]]
        key = original["secondaryKey"]
        source = data[key]
        target = translation.get("female", "")
        
        if not validate_translation_fields(source, target):
            raise RuntimeError(f"Flat JSON translation validation failed for key {key}.")
        data[key] = target
        changed += 1
        
    return changed

# ============================================================
# GENERIC OPEN-FILE TRANSLATION
# ============================================================

def extract_safe_code_strings(content):
    pattern = r'"([^"\\]*(?:\\.[^"\\]*)*)"'
    values = []
    
    for value in re.findall(pattern, content):
        stripped = value.strip()
        if len(stripped) <= 2:
            continue
        if re.search(r"https?://", stripped):
            continue
        if re.search(r"[/\\]", stripped):
            continue
        if re.fullmatch(r"[A-Za-z0-9_.:-]+", stripped):
            if stripped.lower() not in COMMON_UI_WORDS:
                continue
        values.append(value)
        
    return list(dict.fromkeys(values))

def translate_code_file(client, filepath, terminology, log_func=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False

    strings = extract_safe_code_strings(content)
    if not strings:
        return False

    batch = [
        {
            "index": i, 
            "secondaryKey": value, 
            "female": value, 
            "male": ""
        } for i, value in enumerate(strings)
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = translate_batch(client, batch, terminology)
            translations = result.get("translations", [])
            validation = validate_translations(batch, translations)
            
            if validation["has_error"]:
                raise RuntimeError("Validation failed: " + " | ".join(validation["errors"]))

            by_index = {item["index"]: item for item in translations}
            replacements = []
            
            for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content):
                original = match.group(1)
                if original not in strings:
                    continue
                    
                index = strings.index(original)
                translated = by_index[index].get("female", original)
                
                if not validate_translation_fields(original, translated):
                    raise RuntimeError(f"Invalid code string translation: {original}")
                    
                replacements.append((match.start(1), match.end(1), translated))

            for start, end, replacement in reversed(replacements):
                content = content[:start] + replacement + content[end:]
                
            if replacements:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            return False
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if log_func:
                    log_func("API kotası doldu (15 istek/dakika). Modül 60 saniye beklemeye alındı...")
                time.sleep(60)
                continue
            if attempt >= MAX_RETRIES:
                if log_func:
                    log_func(f"Generic code translation failed: {e}")
                raise
            time.sleep(attempt * 2)
            
    return False

# ============================================================
# REDSCRIPT CONFIG FRAMEWORK (JSON & TXT)
# ============================================================

def extract_redscript_config_values(data, strings_set):
    if isinstance(data, dict):
        for k, v in data.items():
            if k in REDSCRIPT_KEYS and isinstance(v, str) and len(v.strip()) > 1:
                strings_set.add(v)
            else:
                extract_redscript_config_values(v, strings_set)
    elif isinstance(data, list):
        for item in data:
            extract_redscript_config_values(item, strings_set)

def translate_redscript_config_file(client, filepath, terminology, log_func=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return False

    strings_set = set()
    extract_redscript_config_values(data, strings_set)
    strings = list(strings_set)
    
    if not strings:
        return False

    if log_func:
        log_func(f"  -> Bulunan metin sayısı: {len(strings)}")

    batch = [
        {
            "index": i, 
            "secondaryKey": val, 
            "female": val, 
            "male": ""
        } for i, val in enumerate(strings)
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if log_func:
                log_func(f"  -> Gemini API'den yanıt bekleniyor (Deneme {attempt})...")

            result = translate_batch(client, batch, terminology)
            translations = result.get("translations", [])
            validation = validate_translations(batch, translations)
            
            if validation["has_error"]:
                raise RuntimeError("Config JSON Validation failed.")

            if log_func:
                log_func("  -> Çeviri başarılı, dosyaya yazılıyor...")

            by_index = {item["index"]: item for item in translations}
            
            def replace_values(d):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if k in REDSCRIPT_KEYS and isinstance(v, str) and v in strings:
                            d[k] = by_index[strings.index(v)].get("female", v)
                        else:
                            replace_values(v)
                elif isinstance(d, list):
                    for item in d:
                        replace_values(item)
                    
            replace_values(data)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            if log_func:
                log_func("  -> İşlem tamamlandı.")
            return True
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if log_func:
                    log_func("API kotası doldu (15 istek/dakika). Modül 60 saniye beklemeye alındı...")
                time.sleep(60)
                continue
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(attempt * 2)
            
    return False

def translate_bbcode_txt_file(client, filepath, terminology, log_func=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return False

    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and re.search(r'[a-zA-Z]', p)]
    paragraphs = list(dict.fromkeys(paragraphs))
    
    if not paragraphs:
        return False

    if log_func:
        log_func(f"  -> Bulunan paragraf sayısı: {len(paragraphs)}")

    batch = [
        {
            "index": i, 
            "secondaryKey": p, 
            "female": p, 
            "male": ""
        } for i, p in enumerate(paragraphs)
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if log_func:
                log_func(f"  -> Gemini API'den yanıt bekleniyor (Deneme {attempt}). Bu uzun sürebilir...")

            result = translate_batch(client, batch, terminology)
            translations = result.get("translations", [])
            validation = validate_translations(batch, translations)
            
            if validation["has_error"]:
                raise RuntimeError("BBCode TXT Validation failed.")

            if log_func:
                log_func("  -> Çeviri başarılı, dosyaya yazılıyor...")

            by_index = {item["index"]: item for item in translations}
            
            for i, p in enumerate(paragraphs):
                translated_p = by_index[i].get("female", p)
                content = content.replace(p, translated_p)
                
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            if log_func:
                log_func("  -> İşlem tamamlandı.")
            return True
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if log_func:
                    log_func("API kotası doldu (15 istek/dakika). Modül 60 saniye beklemeye alındı...")
                time.sleep(60)
                continue
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(attempt * 2)
            
    return False

# ============================================================
# CODEWARE LOCALIZATION
# ============================================================

CODEWARE_PACKAGE_RE = re.compile(
    r"(public\s+class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s+extends\s+ModLocalizationPackage\b)", 
    re.MULTILINE
)
CODEWARE_TEXT_RE = re.compile(
    r'(this\.Text\(\s*")((?:[^"\\]|\\.)*)("\s*,\s*")((?:[^"\\]|\\.)*)(")', 
    re.MULTILINE
)
CODEWARE_PROVIDER_RE = re.compile(
    r"extends\s+ModLocalizationProvider\b", 
    re.MULTILINE
)

def is_codeware_package_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False
    return CODEWARE_PACKAGE_RE.search(content) is not None and "this.Text(" in content

def is_codeware_provider_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False
    return CODEWARE_PROVIDER_RE.search(content) is not None and "GetPackage" in content

def get_codeware_package_class(content):
    match = CODEWARE_PACKAGE_RE.search(content)
    return match.group(2) if match else None

def codeware_class_name_for_target(target_language):
    words = re.findall(r"[A-Za-z0-9]+", target_language)
    return "".join(word[:1].upper() + word[1:] for word in words) if words else "Translated"

def extract_codeware_entries(content):
    return [
        {
            "index": index, 
            "secondaryKey": match.group(2), 
            "female": match.group(4), 
            "male": "", 
            "value_start": match.start(4), 
            "value_end": match.end(4)
        } for index, match in enumerate(CODEWARE_TEXT_RE.finditer(content))
    ]

def translate_codeware_package(client, filepath, output_filepath, terminology, target_class_name, log_func=None):
    with open(filepath, "r", encoding="utf-8") as f:
        source_content = f.read()
        
    entries = extract_codeware_entries(source_content)
    if not entries:
        return False

    translations_by_index = {}
    batches = create_batches(entries, BATCH_SIZE)
    
    for batch_number, batch in enumerate(batches, start=1):
        if log_func:
            log_func(f"Codeware localization batch {batch_number}/{len(batches)}")
            
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = translate_batch(client, batch, terminology)
                translations = result.get("translations", [])
                validation = validate_translations(batch, translations)
                
                if validation["has_error"]:
                    raise RuntimeError("Codeware validation failed: " + " | ".join(validation["errors"]))

                terminology = merge_terminology(terminology, result.get("newTerminology", []))
                save_terminology(terminology)
                
                for item in translations:
                    translations_by_index[item["index"]] = item
                success = True
                break
                
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if log_func:
                        log_func("API kotası doldu (15 istek/dakika). Modül 60 saniye beklemeye alındı...")
                    time.sleep(60)
                    continue
                if attempt >= MAX_RETRIES:
                    raise
                time.sleep(attempt * 2)
                
        if not success:
            raise RuntimeError(f"Codeware batch {batch_number} failed.")

    translated_content = source_content
    replacements = []
    
    for entry in entries:
        translation = translations_by_index.get(entry["index"])
        if translation is None:
            raise RuntimeError(f"Missing Codeware translation for {entry['secondaryKey']}")
            
        source = entry["female"]
        target = translation.get("female", "")
        
        if not validate_translation_fields(source, target):
            raise RuntimeError(f"Invalid Codeware translation for {entry['secondaryKey']}")
            
        replacements.append((entry["value_start"], entry["value_end"], target))

    for start, end, replacement in reversed(replacements):
        translated_content = translated_content[:start] + replacement + translated_content[end:]
        
    translated_content = CODEWARE_PACKAGE_RE.sub(
        lambda match: f"{match.group(1)}{target_class_name}{match.group(3)}", 
        translated_content, 
        count=1
    )
    
    Path(output_filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(translated_content)
        
    return True

def update_codeware_provider(provider_filepath, target_code, target_class_name):
    with open(provider_filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    case_re = re.compile(
        rf'case\s+n"{re.escape(target_code)}"\s*:\s*\n?\s*return\s+new\s+([A-Za-z_][A-Za-z0-9_]*)\(\);', 
        re.MULTILINE
    )
    replacement = f'case n"{target_code}":\n        return new {target_class_name}();'

    if case_re.search(content):
        content = case_re.sub(replacement, content, count=1)
    else:
        marker = re.search(r"(switch\s+language\s*\{\n)", content)
        if not marker:
            raise RuntimeError(f"Codeware GetPackage switch not found: {provider_filepath}")
        content = content[:marker.end()] + "      " + replacement + "\n" + content[marker.end():]

    with open(provider_filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    return True

# ============================================================
# MAIN
# ============================================================

def main():
    actual_input = find_input_file()
    if not actual_input:
        raise FileNotFoundError("Source JSON file not found.")
        
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    
    client = genai.Client(api_key=api_key)
    data = load_json(OUTPUT_FILE) if os.path.exists(OUTPUT_FILE) else load_json(actual_input)
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
    print(f"Target language: {TARGET_LANGUAGE}\nEntries: {len(entries)}\nBatch size: {BATCH_SIZE}")

    batches = create_batches(entries, BATCH_SIZE)
    terminology = load_terminology()
    checkpoint = load_checkpoint()
    completed = set(checkpoint.get("completed_batches", []))
    print(f"Completed batches: {len(completed)}/{len(batches)}")

    for batch_index, batch in enumerate(batches):
        if batch_index in completed:
            print(f"BATCH {batch_index + 1}/{len(batches)} already completed, skipping.")
            continue

        print(f"\nBATCH {batch_index + 1}/{len(batches)}")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = translate_batch(client, batch, terminology)
                translations = result.get("translations", [])
                print(f"Translations received: {len(translations)}")

                validation = validate_translations(batch, translations)
                if validation["has_error"]:
                    print("Validation failed: " + " | ".join(validation["errors"]))
                    if attempt < MAX_RETRIES:
                        time.sleep(attempt * 2)
                        continue
                    raise RuntimeError("Batch failed validation after maximum retries.")

                terminology = merge_terminology(terminology, result.get("newTerminology", []))
                save_terminology(terminology)

                if mode == "archive":
                    changed = apply_archive_translations(data, batch, translations)
                else:
                    changed = apply_flat_translations(data, batch, translations)
                    
                if changed != len(batch):
                    raise RuntimeError(f"Applied {changed}/{len(batch)} entries.")

                save_json(OUTPUT_FILE, data)
                completed.add(batch_index)
                save_checkpoint(completed)

                print("✓ BATCH COMPLETED")
                break
                
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print("API kotası doldu (15 istek/dakika). Modül 60 saniye beklemeye alındı...")
                    time.sleep(60)
                    continue
                if attempt >= MAX_RETRIES:
                    raise
                print(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                time.sleep(attempt * 2)
                
        time.sleep(2)

    print("============================================================")
    print("TRANSLATION COMPLETED")
    print("============================================================")
    print(f"Output: {OUTPUT_FILE}\nCompleted batches: {len(completed)}/{len(batches)}")

if __name__ == "__main__":
    main()