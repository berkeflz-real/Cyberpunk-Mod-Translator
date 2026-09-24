import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import translator

# ============================================================
VERSION = "1.0.3"

# CONFIGURATION
# ============================================================

try:
    BASE_DIR = Path(__compiled__.containing_dir)
except NameError:
    BASE_DIR = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )

WOLVENKIT_DIR = BASE_DIR / "WolvenKit.Console-9.0.1"
WOLVENKIT = WOLVENKIT_DIR / "WolvenKit.CLI.exe"

CONFIG_FILE = BASE_DIR / "config.json"

SOURCE_CODE = "en-us"

LANGUAGES = {
    "Türkçe": ("tr-tr", "Turkish"),
    "English (İngilizce)": ("en-us", "English"),
    "Deutsch (Almanca)": ("de-de", "German"),
    "Español (İspanyolca)": ("es-es", "Spanish"),
    "Español Latino (Latin Amerika İspanyolcası)": ("es-mx", "Latin American Spanish"),
    "Français (Fransızca)": ("fr-fr", "French"),
    "Italiano (İtalyanca)": ("it-it", "Italian"),
    "Polski (Lehçe)": ("pl-pl", "Polish"),
    "Русский (Rusça)": ("ru-ru", "Russian"),
    "한국어 (Korece)": ("kr-kr", "Korean"),
    "日本語 (Japonca)": ("jp-jp", "Japanese"),
    "简体中文 (Basitleştirilmiş Çince)": ("zh-cn", "Simplified Chinese"),
    "繁體中文 (Geleneksel Çince)": ("zh-tw", "Traditional Chinese"),
    "Українська (Ukraynaca)": ("ua-ua", "Ukrainian"),
    "Čeština (Çekçe)": ("cz-cz", "Czech"),
    "Magyar (Macarca)": ("hu-hu", "Hungarian"),
    "Português Brasileiro (Brezilya Portekizcesi)": ("pt-br", "Brazilian Portuguese"),
    "ภาษาไทย (Tayca)": ("th-th", "Thai"),
    "العربية (Arapça)": ("ar-ar", "Arabic"),
}

UI_TEXT = {
    "English": {
        "title": "Cyberpunk 2077 Universal Mod Translator",
        "translation": "Translation Center",
        "review": "Review & Edit (Coming Soon)",
        "guide": "User Guide",
        "ui_language": "UI Language:",
        "theme": "Theme:",
        "black_mode": "Black Mode",
        "source": "Source Mod (.archive or .zip):",
        "output": "Output Folder:",
        "api": "Gemini API Key:",
        "target": "Target Language:",
        "browse": "Browse...",
        "start": "START TRANSLATION",
        "log": "Operation Log",
        "clear": "Clear Log",
        "review_file": "Translated JSON File:",
        "load": "Load",
        "key": "Key / Index",
        "text": "Translated Text",
        "edit": "Edit Selected Text:",
        "apply": "Apply",
        "save": "Save JSON",
        "done": "Completed",
        "done_warning": "Completed with warnings",
        "warning": "Warning",
        "error": "Error",
        "fill": "Please fill in all required fields.",
        "source_missing": "Source mod not found.",
        "invalid_api_title": "Invalid Gemini API Key",
        "invalid_api": "The Gemini API key is invalid or incomplete. Please check that the full key was copied correctly and try again.",
        "status_ready": "Ready.",
        "status_translating": "Translating... API requests may take a while.",
        "status_success": "Translation completed successfully.",
        "status_warning": "Completed with warnings.",
        "status_failed": "Translation failed.",
        "guide_text": (
            "Cyberpunk 2077 Universal Mod Translator - User Guide\n\n"
            "1. HOW TO USE:\n"
            "Select a .archive or .zip mod, choose your target language, enter your Gemini API key, and start the translation.\n\n"
            "2. CRITICAL - GAME DISPLAY LANGUAGE:\n"
            "The in-game display language MUST MATCH the language you translated the mod into. For example, if you translated a mod to German, your game's display language must be set to German; otherwise, the translated text will not appear.\n\n"
            "3. INSTALLATION:\n"
            "For a new installation, install ONLY the generated target-language ZIP. The generated ZIP is a complete replacement package; the original mod does not need to remain installed separately.\n\n"
            "If the original mod is already installed and you do not want to remove/reinstall it, install the generated translation as a separate mod and place it AFTER (below) the original in MO2/Vortex so the translated files take priority.\n\n"
            "4. STABILITY & SAFETY:\n"
            "When a mod contains .archive files, the translator safely modifies only supported localization resources and leaves runtime script files (.reds, .lua, .tweak) untouched to reduce the risk of breaking the mod.\n\n"
            "5. MANUAL INSTALLATION:\n"
            "If you install the translation manually, copy only the archive folder from the generated translation ZIP into your Cyberpunk 2077 game folder.\n\n"
            "WARNING: Manual installation may cause load order conflicts. Use it carefully.\n\n"
            "6. CET MODS:\n"
            "CET-based mods are currently not supported. The translator focuses on supported localization surfaces and does not modify generic CET runtime code.\n"
        ),
    },
    "Türkçe": {
        "title": "Cyberpunk 2077 Universal Mod Translator",
        "translation": "Çeviri Merkezi",
        "review": "İnceleme & Düzenleme (Yakında)",
        "guide": "Kullanım Rehberi",
        "ui_language": "Arayüz Dili:",
        "theme": "Tema:",
        "black_mode": "Siyah Mod",
        "source": "Kaynak Mod (.archive veya .zip):",
        "output": "Çıktı Klasörü:",
        "api": "Gemini API Key:",
        "target": "Hedef Dil:",
        "browse": "Gözat...",
        "start": "ÇEVİRİYİ BAŞLAT",
        "log": "İşlem Günlüğü",
        "clear": "Günlüğü Temizle",
        "review_file": "Çevrilmiş JSON Dosyası:",
        "load": "Yükle",
        "key": "Anahtar / Index",
        "text": "Çeviri Metni",
        "edit": "Seçili Metni Düzenle:",
        "apply": "Uygula",
        "save": "JSON'u Kaydet",
        "done": "Tamamlandı",
        "done_warning": "Uyarılarla tamamlandı",
        "warning": "Uyarı",
        "error": "Hata",
        "fill": "Lütfen gerekli alanların tamamını doldurun.",
        "source_missing": "Kaynak mod bulunamadı.",
        "invalid_api_title": "Geçersiz Gemini API Key",
        "invalid_api": "Gemini API anahtarı geçersiz veya eksik görünüyor. Anahtarın tamamını doğru şekilde kopyaladığınızı kontrol edip tekrar deneyin.",
        "status_ready": "Hazır.",
        "status_translating": "Çeviri yapılıyor... API istekleri biraz sürebilir.",
        "status_success": "Çeviri başarıyla tamamlandı.",
        "status_warning": "Uyarılarla tamamlandı.",
        "status_failed": "Çeviri başarısız oldu.",
        "guide_text": (
            "Cyberpunk 2077 Universal Mod Translator - Kullanım Rehberi\n\n"
            "1. KULLANIM:\n"
            ".archive veya .zip formatındaki modu seçin, hedef dili belirleyin, Gemini API anahtarınızı girin ve çeviriyi başlatın.\n\n"
            "2. ÇOK ÖNEMLİ - OYUNUN GÖRÜNTÜLEME DİLİ:\n"
            "Oyunun görüntüleme dili, modu çevirdiğiniz dille KESİNLİKLE aynı OLMALIDIR. Örneğin bir modu Almancaya çevirdiyseniz, oyunun görüntüleme dili de Almanca olmalıdır; aksi halde çevrilen metinler görünmez.\n\n"
            "3. KURULUM:\n"
            "Yeni bir kurulumda yalnızca oluşturulan hedef dil ZIP dosyasını MO2/Vortex'e kurun. Oluşturulan ZIP, modun tam çevrilmiş/değiştirilmiş paketidir; orijinal modun ayrıca kurulu kalmasına gerek yoktur.\n\n"
            "Orijinal mod zaten kuruluysa ve kaldırıp yeniden kurmak istemiyorsanız, oluşturulan çeviriyi ayrı bir mod olarak ekleyin ve MO2/Vortex'te orijinal modun ALTINDA yerleştirin. Böylece çeviri dosyaları öncelik kazanır.\n\n"
            "4. GÜVENLİK VE KARARLILIK:\n"
            "Modun içinde .archive dosyaları varsa, yalnızca desteklenen yerelleştirme kaynakları güvenli şekilde işlenir; çalışma zamanı kod dosyalarına (.reds, .lua, .tweak) dokunulmaz.\n\n"
            "5. MANUEL KURULUM:\n"
            "Çeviriyi manuel kuracaksanız, yalnızca oluşan çeviri ZIP dosyasının içindeki archive klasörünü Cyberpunk 2077 oyun klasörüne kopyalayabilirsiniz.\n\n"
            "DİKKAT: Manuel kurulum load order çakışmalarına neden olabilir. Dikkatli kullanın.\n\n"
            "6. CET MODLARI:\n"
            "CET tabanlı modlar şu anda desteklenmemektedir. Çevirmen, desteklenen yerelleştirme yüzeylerine odaklanır ve genel CET çalışma zamanı kodlarını değiştirmez.\n"
        ),
    },
}

# ============================================================
# CONFIG
# ============================================================

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "api_key": "",
        "target_language": "Türkçe",
        "ui_language": "English",
        "theme": "default",
    }

def save_config(api_key, target_language, ui_language, theme="default"):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "api_key": api_key,
                "target_language": target_language,
                "ui_language": ui_language,
                "theme": theme,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

# ============================================================
# COMMANDS
# ============================================================

def run_command(command, log_func):
    log_func(
        ">> "
        + " ".join(
            f'"{x}"' if " " in str(x) else str(x)
            for x in command
        )
    )

    creationflags = 0x08000000 if os.name == "nt" else 0

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    for line in process.stdout:
        line = line.rstrip()
        if line:
            log_func(line)

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(
            f"WolvenKit command failed with exit code {process.returncode}."
        )

# ============================================================
# ARCHIVE / ZIP DISCOVERY
# ============================================================


# ============================================================
# ARCHIVE / ZIP DISCOVERY
# ============================================================

def archive_is_cr2w(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"CR2W"
    except Exception:
        return False


def discover_archives(root):
    root = Path(root)
    return sorted(
        [p for p in root.rglob("*.archive") if p.is_file()],
        key=lambda p: str(p).lower(),
    )

KNOWN_LOCALE_CODES = {code.lower() for code, _ in LANGUAGES.values()}
JSON_LOCALIZATION_HINTS = (
    "translation",
    "localization",
    "strings",
    "onscreen",
    "subtitle",
    "journal",
)


def path_has_localization_locale(path, source_code=SOURCE_CODE):
    parts = [part.lower() for part in Path(path).parts]
    if "localization" not in parts:
        return False
    loc_index = parts.index("localization")
    return source_code.lower() in parts[loc_index + 1 :]


def json_filename_has_localization_hint(path):
    name = Path(path).name.lower()
    return any(hint in name for hint in JSON_LOCALIZATION_HINTS)


def resource_has_source_locale(path, source_code=SOURCE_CODE):
    parts = [part.lower() for part in Path(path).parts]
    source = source_code.lower()
    if source in parts:
        return True
    name = Path(path).name.lower()
    return name in {f"{source}.json", f"{source}.json.json"}


def resource_has_other_known_locale(path, source_code=SOURCE_CODE):
    source = source_code.lower()
    for part in Path(path).parts:
        lower = part.lower()
        if lower in KNOWN_LOCALE_CODES and lower != source:
            return True
    return False


def discover_localization_resources(extracted_root):
    root = Path(extracted_root)
    resources = []
    for path in root.rglob("*.json"):
        if not path.is_file() or not archive_is_cr2w(path):
            continue

        if resource_has_other_known_locale(path):
            # We always translate the English source locale. Other language
            # copies stay untouched.
            continue

        source_path = resource_has_source_locale(path, SOURCE_CODE)
        filename_hint = json_filename_has_localization_hint(path)
        if not source_path and not filename_hint:
            continue

        resources.append(path)

    unique = {str(path).lower(): path for path in resources}
    return sorted(unique.values(), key=lambda p: str(p).lower())


def _walk_json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_objects(child)


def is_localization_json_schema(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    if not (
        isinstance(data, dict)
        and isinstance(data.get("Data"), dict)
        and isinstance(data["Data"].get("RootChunk"), dict)
    ):
        return False

    for obj in _walk_json_objects(data):
        obj_type = str(obj.get("$type", "")).lower()
        has_variants = "femaleVariant" in obj or "maleVariant" in obj
        if (
            "localizationpersistence" in obj_type
            and "secondaryKey" in obj
            and has_variants
        ):
            return True
        if "secondaryKey" in obj and has_variants:
            return True
    return False

# ============================================================
# ARCHIVEXL
# ============================================================

def find_source_xl(search_root, archive_path, source_resource_paths):
    root = Path(search_root)
    archive_stem = Path(archive_path).stem.lower()
    resource_texts = []
    for resource in source_resource_paths:
        try:
            resource_texts.append(
                str(resource.relative_to(root)).replace("/", "\\").lower()
            )
        except ValueError:
            resource_texts.append(resource.name.lower())

    best = None
    best_score = 0
    for candidate in sorted(root.rglob("*.xl"), key=lambda p: str(p).lower()):
        try:
            content = candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lower = content.lower()
        score = 0
        if archive_stem in candidate.stem.lower():
            score += 5
        if archive_stem in lower:
            score += 10
        if "localization:" in lower:
            score += 2
        if "en-us:" in lower:
            score += 2
        for resource_text in resource_texts:
            if resource_text and resource_text in lower:
                score += 4
        if score > best_score:
            best_score = score
            best = candidate
    return best


def replace_locale_in_text(text, source_code, target_code):
    return re.sub(
        rf"(?i)\b{re.escape(source_code)}\b",
        target_code,
        text,
    )


def target_path_for_resource(resource, extracted_root, target_code):
    relative = resource.relative_to(extracted_root)
    parts = list(relative.parts)
    source = SOURCE_CODE.lower()
    for index, part in enumerate(parts):
        if part.lower() == source:
            parts[index] = target_code
            return Path(*parts)

    lower_name = relative.name.lower()
    if lower_name in {f"{source}.json", f"{source}.json.json"}:
        return relative.with_name(re.sub(re.escape(source), target_code, relative.name, count=1, flags=re.I))

    # Locale-less resources such as translation_strings.json are consumed at
    # their original path and must be replaced in place.
    return relative


def _language_mapping_blocks(lines):
    language_re = re.compile(
        r"^(?P<indent>[ \t]*)(?P<lang>[a-z]{2}-[a-z]{2})(?P<sep>\s*:\s*)(?P<value>.*?)(?P<nl>\r?\n)?$",
        re.I,
    )
    blocks = []
    i = 0
    while i < len(lines):
        match = language_re.match(lines[i])
        if not match:
            i += 1
            continue
        indent = len(match.group("indent").replace("\t", "    "))
        start = i
        i += 1
        while i < len(lines):
            next_match = language_re.match(lines[i])
            if next_match and len(next_match.group("indent").replace("\t", "    ")) <= indent:
                break
            # Stop at another obvious top-level YAML section if it is at or
            # above the mapping indentation.
            if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip(" \t")) <= indent and ":" in lines[i]:
                break
            i += 1
        blocks.append((start, i, match, indent))
    return blocks


def transform_archive_xl(content, source_code, target_code):
    if source_code.lower() == target_code.lower():
        return content

    lines = content.splitlines(keepends=True)
    blocks = _language_mapping_blocks(lines)
    source_blocks = [block for block in blocks if block[2].group("lang").lower() == source_code.lower()]
    if not source_blocks:
        return content

    target_lower = target_code.lower()
    remove_ranges = []
    for start, end, match, _ in blocks:
        if match.group("lang").lower() == target_lower:
            remove_ranges.append((start, end))

    remove_set = set()
    for start, end in remove_ranges:
        remove_set.update(range(start, end))

    result = []
    source_block_ranges = {(start, end) for start, end, _, _ in source_blocks}
    i = 0
    while i < len(lines):
        if i in remove_set:
            i += 1
            continue

        block = next((b for b in source_blocks if b[0] == i), None)
        if block:
            start, end, match, _ = block
            for j in range(start, end):
                result.append(replace_locale_in_text(lines[j], source_code, target_code))
            i = end
            continue

        result.append(lines[i])
        i += 1

    return "".join(result)


def build_target_xl(source_xl, target_code, output_xl):
    if source_xl is None:
        return False
    try:
        original = source_xl.read_text(encoding="utf-8", errors="ignore")
        # Some ArchiveXL manifests map locale-less resources (for example
        # translation_strings.json) without an en-us language block. In that
        # case the manifest itself must be preserved unchanged because the
        # translated resource stays at the same path.
        if not re.search(r"(?im)^\s*en-us\s*:", original):
            output_xl.write_text(original, encoding="utf-8")
            return True

        transformed = transform_archive_xl(original, SOURCE_CODE, target_code)
        output_xl.write_text(transformed, encoding="utf-8")
        return True
    except Exception:
        return False

# ============================================================
# OUTPUT / TRANSLATOR BRIDGE
# ============================================================

def clean_archive_stem(stem):
    return re.sub(
        r"_(TR|RU|DE|FR|ES|IT|PL|JP|KR|CN|TW|UA|CZ|HU|BR|TH|AR)$",
        "",
        stem,
        flags=re.IGNORECASE,
    )


def make_unique_base(base, used):
    if base not in used:
        used.add(base)
        return base
    number = 2
    while f"{base}_{number}" in used:
        number += 1
    result = f"{base}_{number}"
    used.add(result)
    return result


def package_is_safe_mod_zip(zip_path):
    with zipfile.ZipFile(zip_path, "r") as z:
        names = {name.replace("\\", "/") for name in z.namelist()}
    return any(name.startswith("archive/pc/mod/") for name in names)


def run_translator(
    serialized_json,
    translated_root,
    target_name,
    api_key,
    target_code,
    target_language,
    terminology_seed=None,
    log_func=None,
):
    translated_root = Path(translated_root)
    translated_root.mkdir(parents=True, exist_ok=True)
    output_file = translated_root / target_name
    terminology_file = translated_root / "terminology.json"
    checkpoint_file = translated_root / "checkpoint.json"
    if terminology_seed is not None and Path(terminology_seed).exists() and not terminology_file.exists():
        shutil.copy2(terminology_seed, terminology_file)

    old_values = {
        name: getattr(translator, name)
        for name in (
            "INPUT_FILE",
            "OUTPUT_FILE",
            "TERMINOLOGY_FILE",
            "CHECKPOINT_FILE",
            "TARGET_LANGUAGE",
            "TARGET_CODE",
        )
    }
    old_env = os.environ.get("GEMINI_API_KEY")
    old_stdout = sys.stdout

    translator.INPUT_FILE = str(serialized_json)
    translator.OUTPUT_FILE = str(output_file)
    translator.TERMINOLOGY_FILE = str(terminology_file)
    translator.CHECKPOINT_FILE = str(checkpoint_file)
    translator.TARGET_LANGUAGE = target_language
    translator.TARGET_CODE = target_code
    os.environ["GEMINI_API_KEY"] = api_key

    class LogWriter:
        def write(self, text):
            if text and log_func:
                stripped = text.strip()
                if stripped:
                    log_func(stripped)
            return len(text)

        def flush(self):
            pass

    try:
        sys.stdout = LogWriter()
        translator.main()
    finally:
        sys.stdout = old_stdout
        for name, value in old_values.items():
            setattr(translator, name, value)
        if old_env is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = old_env

    if not output_file.exists():
        raise RuntimeError(
            f"Translator completed without creating {target_name}."
        )
    return output_file


def process_selective_lua_localization(stage_root, client, terminology_file, log_func):
    translated = []
    failures = []
    for path in sorted(Path(stage_root).rglob("*.lua"), key=lambda p: str(p).lower()):
        try:
            if not translator.is_lua_localization_file(path):
                continue
            terminology = translator.load_terminology()
            if translator.translate_lua_localization_file(
                client, str(path), terminology, log_func
            ):
                translated.append(path)
        except Exception as error:
            warning = f"Lua localization failed for {path.name}: {error}"
            failures.append(warning)
            log_func(f"WARNING: {warning}")
    return translated, failures

# ============================================================
# MAIN TRANSLATION PIPELINE
# ============================================================

def run_translation(
    input_path,
    output_folder,
    api_key,
    selected_language,
    log_func,
    progress_func,
):
    input_path = Path(input_path)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    target_code, target_language = LANGUAGES[selected_language]
    target_short = target_code.split("-")[0].upper()
    clean_stem = clean_archive_stem(input_path.stem)
    job_id = f"{clean_stem}_{target_code}"
    work_root = output_folder / "_cytranslator_work" / job_id
    work_root.mkdir(parents=True, exist_ok=True)

    stage_root = work_root / "MO2"
    mod_root = stage_root / "archive" / "pc" / "mod"
    mod_root.mkdir(parents=True, exist_ok=True)
    shared_terms = work_root / "terminology.json"
    if not shared_terms.exists():
        shared_terms.write_text(
            json.dumps({"languages": {}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    translation_warnings = []
    used_output_names = set()

    try:
        source_root = work_root / "source"
        if input_path.suffix.lower() == ".zip":
            # Refresh only source/stage. Resource checkpoints and translated outputs
            # live separately and survive restarts.
            if source_root.exists():
                shutil.rmtree(source_root, ignore_errors=True)
            if stage_root.exists():
                shutil.rmtree(stage_root, ignore_errors=True)
            source_root.mkdir(parents=True, exist_ok=True)
            log_func(f"Unpacking source ZIP: {input_path.name}")
            with zipfile.ZipFile(input_path, "r") as z:
                z.extractall(source_root)
            shutil.copytree(source_root, stage_root, dirs_exist_ok=True)
            archives = discover_archives(source_root)
        else:
            if stage_root.exists():
                shutil.rmtree(stage_root, ignore_errors=True)
            source_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, source_root / input_path.name)
            stage_root.mkdir(parents=True, exist_ok=True)
            mod_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, mod_root / input_path.name)
            archives = [input_path]

        if archives:
            log_func(f"Found {len(archives)} archive file(s).")
            log_func(
                "Safety mode: runtime .reds/.lua/.tweak files are protected. "
                "Dedicated localization surfaces, including ArchiveXL OnScreen resources, may still be processed safely."
            )

            from google import genai
            client = genai.Client(api_key=api_key)

            for archive_index, archive_path in enumerate(archives, 1):
                log_func("")
                log_func(
                    f"=== ARCHIVE {archive_index}/{len(archives)}: {archive_path.name} ==="
                )

                archive_work = work_root / f"archive_{archive_index}"
                extracted = archive_work / "extracted"
                pack = archive_work / "pack"
                packed = archive_work / "packed"
                for directory in (extracted, pack, packed):
                    if directory.exists():
                        shutil.rmtree(directory, ignore_errors=True)
                    directory.mkdir(parents=True, exist_ok=True)

                run_command(
                    [str(WOLVENKIT), "extract", str(archive_path), "-o", str(extracted)],
                    log_func,
                )
                resources = discover_localization_resources(extracted)
                if resources:
                    log_func(
                        f"Found {len(resources)} localization candidate(s) in source-language resources."
                    )
                else:
                    log_func(
                        "INFO: No localization candidates found in this archive; archive will be copied unchanged."
                    )

                source_xl = (
                    find_source_xl(source_root, archive_path, resources)
                    if resources and input_path.suffix.lower() == ".zip"
                    else None
                )
                if source_xl:
                    log_func(f"Source ArchiveXL file: {source_xl}")

                shutil.copytree(extracted, pack, dirs_exist_ok=True)
                successful_resources = 0

                for resource_index, resource in enumerate(resources, 1):
                    relative_source = resource.relative_to(extracted)
                    relative_target = target_path_for_resource(
                        resource, extracted, target_code
                    )
                    resource_work = archive_work / "resources" / str(resource_index)
                    serialized_root = resource_work / "serialized"
                    translated_root = resource_work / "translated"
                    deserialized_root = resource_work / "deserialized"
                    for directory in (
                        serialized_root,
                        translated_root,
                        deserialized_root,
                    ):
                        directory.mkdir(parents=True, exist_ok=True)

                    lower_parts = [part.lower() for part in relative_source.parts]
                    if "onscreens" in lower_parts:
                        label = "OnScreen localization"
                    elif json_filename_has_localization_hint(resource):
                        label = "Localization candidate by filename"
                    else:
                        label = "Localization"
                    log_func(
                        f"{label} {resource_index}/{len(resources)}: {relative_source}"
                    )

                    run_command(
                        [
                            str(WOLVENKIT),
                            "convert",
                            "serialize",
                            str(resource),
                            "-o",
                            str(serialized_root),
                        ],
                        log_func,
                    )
                    serialized_candidates = list(serialized_root.rglob("*.json.json"))
                    if not serialized_candidates:
                        serialized_candidates = list(serialized_root.rglob("*.json"))
                    if not serialized_candidates:
                        raise RuntimeError(
                            f"Serialize produced no JSON for {relative_source}."
                        )
                    serialized_json = serialized_candidates[0]

                    if not is_localization_json_schema(serialized_json):
                        log_func(
                            "INFO: JSON candidate did not match the supported localization schema; "
                            "original resource will be preserved unchanged."
                        )
                        continue
                    log_func("  -> Supported localization schema confirmed.")

                    translated_json = run_translator(
                        serialized_json,
                        translated_root,
                        relative_target.name,
                        api_key,
                        target_code,
                        target_language,
                        shared_terms,
                        log_func,
                    )
                    run_command(
                        [
                            str(WOLVENKIT),
                            "convert",
                            "deserialize",
                            str(translated_json),
                            "-o",
                            str(deserialized_root),
                        ],
                        log_func,
                    )

                    cr2w_candidates = [
                        p for p in deserialized_root.rglob("*")
                        if p.is_file() and archive_is_cr2w(p)
                    ]
                    if not cr2w_candidates:
                        raise RuntimeError(
                            f"Deserialize produced no CR2W for {relative_source}."
                        )
                    translated_cr2w = cr2w_candidates[0]

                    source_copy = pack / relative_source
                    target_copy = pack / relative_target
                    if source_copy.exists() and source_copy != target_copy:
                        source_copy.unlink()
                    target_copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(translated_cr2w, target_copy)
                    successful_resources += 1

                # Codeware fallback: translate the English package in place.
                codeware_packages = [
                    p
                    for p in extracted.rglob("*.reds")
                    if p.is_file() and translator.is_codeware_package_file(p)
                ]
                codeware_changed = False
                if codeware_packages:
                    old_values = (
                        translator.TARGET_LANGUAGE,
                        translator.TARGET_CODE,
                        translator.TERMINOLOGY_FILE,
                        translator.CHECKPOINT_FILE,
                    )
                    translator.TARGET_LANGUAGE = target_language
                    translator.TARGET_CODE = target_code
                    translator.TERMINOLOGY_FILE = str(shared_terms)
                    translator.CHECKPOINT_FILE = str(
                        work_root / "codeware_checkpoint.json"
                    )
                    try:
                        for package in codeware_packages:
                            relative = package.relative_to(extracted)
                            output_package = pack / relative
                            log_func(
                                f"Codeware localization fallback: translating the English package in place."
                            )
                            changed = translator.translate_codeware_package(
                                client,
                                str(package),
                                str(output_package),
                                translator.load_terminology(),
                                "English",
                                log_func,
                            )
                            codeware_changed = codeware_changed or bool(changed)
                    finally:
                        (
                            translator.TARGET_LANGUAGE,
                            translator.TARGET_CODE,
                            translator.TERMINOLOGY_FILE,
                            translator.CHECKPOINT_FILE,
                        ) = old_values

                if successful_resources or codeware_changed:
                    run_command(
                        [
                            str(WOLVENKIT),
                            "pack",
                            str(pack),
                            "-o",
                            str(packed),
                        ],
                        log_func,
                    )
                    pack_candidates = list(packed.rglob("*.archive"))
                    if not pack_candidates:
                        raise RuntimeError(
                            f"WolvenKit produced no archive for {archive_path.name}."
                        )
                    packed_archive = next(
                        (p for p in pack_candidates if p.name.lower() == "pack.archive"),
                        pack_candidates[0],
                    )

                    final_base = make_unique_base(
                        f"{clean_archive_stem(archive_path.stem)}_{target_short}",
                        used_output_names,
                    )
                    final_archive = mod_root / f"{final_base}.archive"
                    shutil.copy2(packed_archive, final_archive)

                    final_xl = mod_root / f"{final_base}.archive.xl"
                    if build_target_xl(source_xl, target_code, final_xl):
                        pass
                    elif final_xl.exists():
                        final_xl.unlink()

                    if input_path.suffix.lower() == ".zip":
                        staged_original = stage_root / archive_path.relative_to(source_root)
                        if staged_original.exists():
                            staged_original.unlink()
                        if source_xl is not None:
                            try:
                                staged_xl = stage_root / source_xl.relative_to(source_root)
                                if staged_xl.exists():
                                    staged_xl.unlink()
                            except ValueError:
                                pass
                else:
                    log_func("INFO: No supported localization changes were produced; original archive retained.")

        else:
            # Loose/open-file mode: process only dedicated, safe surfaces.
            log_func("No .archive files found. Open-file translation mode is enabled.")
            all_files = [p for p in stage_root.rglob("*") if p.is_file()]
            runtime_skipped = [
                p
                for p in all_files
                if p.suffix.lower() in {".reds", ".tweak", ".yaml"}
                and not translator.is_codeware_package_file(p)
            ]
            if runtime_skipped:
                log_func(
                    f"Safety mode: skipped {len(runtime_skipped)} unsupported runtime/code file(s) from generic translation."
                )
            log_func(
                "Safety mode: generic runtime-source translation is disabled; dedicated localization surfaces are handled separately."
            )

            from google import genai
            client = genai.Client(api_key=api_key)
            old_values = (
                translator.TARGET_LANGUAGE,
                translator.TARGET_CODE,
                translator.TERMINOLOGY_FILE,
                translator.CHECKPOINT_FILE,
            )
            translator.TARGET_LANGUAGE = target_language
            translator.TARGET_CODE = target_code
            translator.TERMINOLOGY_FILE = str(shared_terms)
            translator.CHECKPOINT_FILE = str(work_root / "open_localization_checkpoint.json")
            try:
                for package in all_files:
                    if package.suffix.lower() == ".reds" and translator.is_codeware_package_file(package):
                        log_func(
                            "Codeware localization fallback: translating the English package in place."
                        )
                        translator.translate_codeware_package(
                            client,
                            str(package),
                            str(package),
                            translator.load_terminology(),
                            "English",
                            log_func,
                        )
                for file in all_files:
                    relative_parts = set(file.relative_to(stage_root).parts)
                    if "RedscriptConfigFramework" in relative_parts:
                        try:
                            if file.suffix.lower() == ".json":
                                translator.translate_redscript_config_file(
                                    client,
                                    str(file),
                                    translator.load_terminology(),
                                    log_func,
                                )
                            elif file.suffix.lower() == ".txt":
                                translator.translate_bbcode_txt_file(
                                    client,
                                    str(file),
                                    translator.load_terminology(),
                                    log_func,
                                )
                        except Exception as error:
                            warning = f"Open-file translation failed for {file.name}: {error}"
                            translation_warnings.append(warning)
                            log_func(f"WARNING: {warning}")
            finally:
                (
                    translator.TARGET_LANGUAGE,
                    translator.TARGET_CODE,
                    translator.TERMINOLOGY_FILE,
                    translator.CHECKPOINT_FILE,
                ) = old_values

        # Lua localization is a loose-file surface. Keep it outside archive packing.
        from google import genai
        client = genai.Client(api_key=api_key)
        old_values = (
            translator.TARGET_LANGUAGE,
            translator.TARGET_CODE,
            translator.TERMINOLOGY_FILE,
            translator.CHECKPOINT_FILE,
        )
        old_env = os.environ.get("GEMINI_API_KEY")
        translator.TARGET_LANGUAGE = target_language
        translator.TARGET_CODE = target_code
        translator.TERMINOLOGY_FILE = str(shared_terms)
        translator.CHECKPOINT_FILE = str(work_root / "lua_checkpoint.json")
        os.environ["GEMINI_API_KEY"] = api_key
        try:
            _, lua_failures = process_selective_lua_localization(
                stage_root, client, shared_terms, log_func
            )
            translation_warnings.extend(lua_failures)
        finally:
            (
                translator.TARGET_LANGUAGE,
                translator.TARGET_CODE,
                translator.TERMINOLOGY_FILE,
                translator.CHECKPOINT_FILE,
            ) = old_values
            if old_env is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old_env

        final_zip_base = f"{clean_stem}_{target_short}"
        final_zip = output_folder / f"{final_zip_base}.zip"
        if final_zip.exists():
            final_zip.unlink()

        shutil.make_archive(
            str(output_folder / final_zip_base),
            "zip",
            root_dir=stage_root,
        )
        if not final_zip.exists():
            raise RuntimeError("MO2 ZIP could not be created.")

        log_func("")
        log_func(f"MO2-ready ZIP created: {final_zip}")
        return {"zip": final_zip, "warnings": translation_warnings}

    finally:
        # Keep the persistent checkpoint/terminology tree for resume. The temporary
        # source/stage tree is cleaned after a finished job.
        for path in (work_root / "source", work_root / "MO2"):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)


class App:
    def __init__(self, root):
        self.root = root
        self.config = load_config()

        self.current_ui_language = self.config.get("ui_language", "English")
        if self.current_ui_language not in UI_TEXT:
            self.current_ui_language = "English"

        self.root.title(UI_TEXT[self.current_ui_language]["title"])
        self.root.geometry("900x760")
        self.root.minsize(800, 650)

        self.archive_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.api_var = tk.StringVar(value=self.config.get("api_key", ""))
        self.target_var = tk.StringVar(value=self.config.get("target_language", "Türkçe"))

        if self.target_var.get() not in LANGUAGES:
            self.target_var.set("Türkçe")

        self.ui_var = tk.StringVar(value=self.current_ui_language)
        self.black_mode_var = tk.BooleanVar(value=self.config.get("theme", "default") == "black")
        self.style = ttk.Style(self.root)
        self.default_theme = self.style.theme_use()
        self.default_root_bg = self.root.cget("bg")

        self.review_data = None
        self.review_mode = None
        self.translation_running = False

        self.build_ui()
        self.default_text_colors = {
            "log": (self.log_text.cget("bg"), self.log_text.cget("fg"), self.log_text.cget("insertbackground")),
            "guide": (self.guide_text.cget("bg"), self.guide_text.cget("fg"), self.guide_text.cget("insertbackground")),
        }
        self.apply_theme()
        self.update_ui_text()

    def build_ui(self):
        top = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        top.pack(fill="x")

        self.ui_label = ttk.Label(top)
        self.ui_label.pack(side="left")

        self.ui_combo = ttk.Combobox(
            top,
            textvariable=self.ui_var,
            values=["English", "Türkçe"],
            state="readonly",
            width=12,
        )
        self.ui_combo.pack(side="left", padx=(6, 0))
        self.ui_combo.bind("<<ComboboxSelected>>", self.change_ui_language)

        self.theme_label = ttk.Label(top)
        self.theme_label.pack(side="left", padx=(20, 0))

        self.black_mode_check = ttk.Checkbutton(
            top,
            variable=self.black_mode_var,
            command=self.change_theme,
        )
        self.black_mode_check.pack(side="left", padx=(6, 0))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_translate = ttk.Frame(self.notebook, padding=15)
        self.tab_review = ttk.Frame(self.notebook, padding=15)
        self.tab_guide = ttk.Frame(self.notebook, padding=15)

        self.notebook.add(self.tab_translate)
        self.notebook.add(self.tab_review)
        self.notebook.add(self.tab_guide)

        self.build_translation_tab()
        self.build_review_tab()
        self.build_guide_tab()
        self.notebook.tab(self.tab_review, state="disabled")

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 7))
        footer.pack(fill="x")
        self.author_label = ttk.Label(footer, text="berkeflz", font=("Segoe UI", 8))
        self.author_label.pack(side="right")

    def build_translation_tab(self):
        main = self.tab_translate

        self.source_label = ttk.Label(main)
        self.source_label.pack(anchor="w")

        source_frame = ttk.Frame(main)
        source_frame.pack(fill="x", pady=(4, 12))

        self.source_entry = ttk.Entry(source_frame, textvariable=self.archive_var)
        self.source_entry.pack(side="left", fill="x", expand=True)

        self.source_button = ttk.Button(source_frame, command=self.select_archive)
        self.source_button.pack(side="left", padx=(8, 0))

        self.output_label = ttk.Label(main)
        self.output_label.pack(anchor="w")

        output_frame = ttk.Frame(main)
        output_frame.pack(fill="x", pady=(4, 12))

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.pack(side="left", fill="x", expand=True)

        self.output_button = ttk.Button(output_frame, command=self.select_output)
        self.output_button.pack(side="left", padx=(8, 0))

        settings = ttk.Frame(main)
        settings.pack(fill="x", pady=(0, 15))

        api_frame = ttk.Frame(settings)
        api_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.api_label = ttk.Label(api_frame)
        self.api_label.pack(anchor="w")

        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_var, show="*")
        self.api_entry.pack(fill="x")

        target_frame = ttk.Frame(settings)
        target_frame.pack(side="left", fill="x", expand=True)

        self.target_label = ttk.Label(target_frame)
        self.target_label.pack(anchor="w")

        self.target_combo = ttk.Combobox(
            target_frame,
            textvariable=self.target_var,
            values=list(LANGUAGES.keys()),
            state="readonly",
        )
        self.target_combo.pack(fill="x")

        self.start_button = ttk.Button(main, command=self.start_translation)
        self.start_button.pack(fill="x", pady=(0, 10))

        self.status_label = ttk.Label(main)
        self.status_label.pack(anchor="w", pady=(0, 5))

        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 12))

        self.log_label = ttk.Label(main)
        self.log_label.pack(anchor="w")

        log_frame = ttk.Frame(main)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")

        self.log_text.configure(yscrollcommand=scrollbar.set)

    def build_review_tab(self):
        main = self.tab_review

        top = ttk.Frame(main)
        top.pack(fill="x", pady=(0, 10))

        self.review_file_label = ttk.Label(top)
        self.review_file_label.pack(side="left")

        self.review_path_var = tk.StringVar()

        ttk.Entry(top, textvariable=self.review_path_var).pack(side="left", fill="x", expand=True, padx=6)

        self.review_load_button = ttk.Button(top, command=self.load_review_file)
        self.review_load_button.pack(side="left")

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill="both", expand=True)

        self.review_tree = ttk.Treeview(tree_frame, columns=("Key", "Text"), show="headings")
        self.review_tree.heading("Key")
        self.review_tree.heading("Text")
        self.review_tree.column("Key", width=220, stretch=False)
        self.review_tree.column("Text", width=560, stretch=True)
        self.review_tree.pack(side="left", fill="both", expand=True)

        review_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.review_tree.yview)
        review_scroll.pack(side="right", fill="y")

        self.review_tree.configure(yscrollcommand=review_scroll.set)
        self.review_tree.bind("<<TreeviewSelect>>", self.on_review_select)

        self.review_edit_label = ttk.Label(main)
        self.review_edit_label.pack(anchor="w", pady=(10, 0))

        self.review_edit_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.review_edit_var).pack(fill="x", pady=5)

        button_frame = ttk.Frame(main)
        button_frame.pack(fill="x")

        self.review_apply_button = ttk.Button(button_frame, command=self.apply_review_edit)
        self.review_apply_button.pack(side="left")

        self.review_save_button = ttk.Button(button_frame, command=self.save_review_file)
        self.review_save_button.pack(side="right")

    def build_guide_tab(self):
        self.guide_text = tk.Text(self.tab_guide, wrap="word", font=("Segoe UI", 10))
        self.guide_text.pack(fill="both", expand=True)

    def update_ui_text(self):
        t = UI_TEXT[self.current_ui_language]

        self.root.title(t["title"])
        self.notebook.tab(self.tab_translate, text=t["translation"])
        self.notebook.tab(self.tab_review, text=t["review"])
        self.notebook.tab(self.tab_guide, text=t["guide"])

        self.ui_label.configure(text=t["ui_language"])
        self.theme_label.configure(text=t["theme"])
        self.black_mode_check.configure(text=t["black_mode"])
        self.source_label.configure(text=t["source"])
        self.output_label.configure(text=t["output"])
        self.api_label.configure(text=t["api"])
        self.target_label.configure(text=t["target"])
        self.source_button.configure(text=t["browse"])
        self.output_button.configure(text=t["browse"])
        self.start_button.configure(text=t["start"])
        self.log_label.configure(text=t["log"])
        if not self.translation_running:
            self.status_label.configure(text=t["status_ready"])

        self.review_file_label.configure(text=t["review_file"])
        self.review_load_button.configure(text=t["load"])
        self.review_tree.heading("Key", text=t["key"])
        self.review_tree.heading("Text", text=t["text"])
        self.review_edit_label.configure(text=t["edit"])
        self.review_apply_button.configure(text=t["apply"])
        self.review_save_button.configure(text=t["save"])

        self.guide_text.configure(state="normal")
        self.guide_text.delete("1.0", "end")
        self.guide_text.insert("1.0", t["guide_text"])
        self.guide_text.configure(state="disabled")

    def change_ui_language(self, event=None):
        self.current_ui_language = self.ui_var.get()
        save_config(
            self.api_var.get(),
            self.target_var.get(),
            self.current_ui_language,
            "black" if self.black_mode_var.get() else "default",
        )
        self.update_ui_text()

    def change_theme(self):
        self.apply_theme()
        save_config(
            self.api_var.get(),
            self.target_var.get(),
            self.current_ui_language,
            "black" if self.black_mode_var.get() else "default",
        )

    def apply_theme(self):
        if self.black_mode_var.get():
            self.style.theme_use("clam")

            # Soft near-black palette: dark enough for the requested Black Mode
            # without the harsh pure-black look.
            bg = "#15171c"
            surface = "#1b1e24"
            surface2 = "#111319"
            field = "#20242b"
            text = "#e7ebf0"
            muted = "#aeb6c2"
            accent = "#58d7ef"
            selected = "#25303b"

            self.style.configure("TFrame", background=bg)
            self.style.configure("TLabel", background=bg, foreground=text)
            self.style.configure(
                "TButton",
                background=surface,
                foreground=text,
                bordercolor="#343a44",
                padding=6,
            )
            self.style.map(
                "TButton",
                background=[("active", "#2a3039"), ("pressed", "#242a32"), ("disabled", "#181a1f")],
                foreground=[("disabled", "#68717d")],
            )
            self.style.configure("TCheckbutton", background=bg, foreground=text)
            self.style.map(
                "TCheckbutton",
                foreground=[("disabled", "#68717d"), ("active", accent)],
                background=[("active", bg)],
            )
            self.style.configure(
                "TCombobox",
                fieldbackground=field,
                background=surface,
                foreground=text,
                arrowcolor=muted,
                bordercolor="#343a44",
                lightcolor="#343a44",
                darkcolor="#343a44",
            )
            self.style.map(
                "TCombobox",
                fieldbackground=[("readonly", field), ("disabled", "#181a1f")],
                foreground=[("readonly", text), ("disabled", "#68717d")],
            )
            self.style.configure(
                "TEntry",
                fieldbackground=field,
                foreground=text,
                insertcolor=accent,
                bordercolor="#343a44",
                lightcolor="#343a44",
                darkcolor="#343a44",
            )
            self.style.map(
                "TEntry",
                fieldbackground=[("disabled", "#181a1f")],
                foreground=[("disabled", "#68717d")],
            )
            self.style.configure("TNotebook", background=bg, borderwidth=0, tabmargins=(2, 2, 2, 0))
            self.style.configure(
                "TNotebook.Tab",
                background=surface,
                foreground=text,
                padding=(12, 6),
                bordercolor="#343a44",
            )
            self.style.map(
                "TNotebook.Tab",
                background=[("selected", selected)],
                foreground=[("selected", accent)],
            )
            self.style.configure(
                "Treeview",
                background=surface2,
                fieldbackground=surface2,
                foreground=text,
                bordercolor="#343a44",
            )
            self.style.configure(
                "Treeview.Heading",
                background=surface,
                foreground=text,
                bordercolor="#343a44",
            )
            self.style.configure(
                "Horizontal.TProgressbar",
                troughcolor=surface2,
                background=accent,
                bordercolor=surface2,
                lightcolor=accent,
                darkcolor=accent,
            )
            self.root.configure(bg=bg)

            text_colors = {
                "log": ("#0f1115", "#dfe5eb", accent),
                "guide": ("#0f1115", "#dfe5eb", accent),
            }
            self._style_combobox_popdown(self.ui_combo)
            self._style_combobox_popdown(self.target_combo)
        else:
            self.style.theme_use(self.default_theme)
            self.root.configure(bg=self.default_root_bg)
            text_colors = self.default_text_colors

        for name, widget in (("log", self.log_text), ("guide", self.guide_text)):
            bg, fg, insert = text_colors[name]
            widget.configure(bg=bg, fg=fg, insertbackground=insert)

    def _style_combobox_popdown(self, combo):
        """Style the native ttk Combobox drop-down list in Black Mode when Tk exposes it."""
        if not self.black_mode_var.get():
            return
        try:
            popdown = self.root.tk.call("ttk::combobox::PopdownWindow", str(combo))
            listbox = f"{popdown}.f.l"
            self.root.tk.call(
                listbox,
                "configure",
                "-background", "#20242b",
                "-foreground", "#e7ebf0",
                "-selectbackground", "#33424f",
                "-selectforeground", "#58d7ef",
                "-highlightthickness", 0,
                "-borderwidth", 0,
            )
        except tk.TclError:
            pass

    def select_archive(self):
        path = filedialog.askopenfilename(
            title="Select source mod",
            filetypes=[
                ("Cyberpunk Mods", "*.archive *.zip"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.archive_var.set(path)
            if not self.output_var.get():
                self.output_var.set(str(Path(path).parent))

    def select_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_var.set(path)

    def log(self, message):
        # Keep credential errors readable instead of dumping the raw Gemini
        # authentication payload into the operation log. Other API errors,
        # including rate-limit messages, are left intact.
        display_message = self._friendly_error_message(message)

        def update():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", str(display_message) + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, update)

    def set_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))

    def set_status(self, message):
        self.root.after(0, lambda: self.status_label.configure(text=message))

    def set_translation_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        combo_state = "readonly" if enabled else "disabled"
        self.source_entry.configure(state=state)
        self.source_button.configure(state=state)
        self.output_entry.configure(state=state)
        self.output_button.configure(state=state)
        self.api_entry.configure(state=state)
        self.target_combo.configure(state=combo_state)
        self.ui_combo.configure(state=combo_state)
        self.black_mode_check.configure(state=state)

    def start_translation(self):
        archive = self.archive_var.get().strip()
        output = self.output_var.get().strip()
        api_key = self.api_var.get().strip()
        target = self.target_var.get()
        t = UI_TEXT[self.current_ui_language]

        if not archive or not output or not api_key:
            messagebox.showerror(t["error"], t["fill"])
            return

        if not Path(archive).exists():
            messagebox.showerror(t["error"], t["source_missing"])
            return

        if not WOLVENKIT.exists():
            messagebox.showerror(
            t["error"],
            "WolvenKit Console was not found.\n\n"
            "Make sure the 'WolvenKit.Console-9.0.1' folder is located "
            "next to the translator application."
            )
            return

        save_config(
            api_key,
            target,
            self.current_ui_language,
            "black" if self.black_mode_var.get() else "default",
        )

        self.translation_running = True
        self.set_translation_controls_enabled(False)
        self.start_button.configure(state="disabled")
        self.progress.stop()
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_label.configure(text=UI_TEXT[self.current_ui_language]["status_translating"])

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        threading.Thread(
            target=self.worker,
            args=(archive, output, api_key, target),
            daemon=True,
        ).start()

    def _friendly_error_message(self, error):
        message = str(error)
        lower = message.lower()

        if (
            "401 unauthenticated" in lower
            or "access_token_type_unsupported" in lower
            or "invalid api key" in lower
            or "invalid_api_key" in lower
            or "authentication credentials" in lower
        ):
            return UI_TEXT[self.current_ui_language]["invalid_api"]
        if "503" in lower or "unavailable" in lower:
            return "Gemini is temporarily unavailable after multiple retry attempts. Please try again later."

        return message

    def worker(self, archive, output, api_key, target):
        t = UI_TEXT[self.current_ui_language]
        try:
            result = run_translation(
                input_path=archive,
                output_folder=output,
                api_key=api_key,
                selected_language=target,
                log_func=self.log,
                progress_func=self.set_progress,
            )

            warnings = result.get("warnings", [])
            self.log("")
            self.log("============================================================")
            if warnings:
                self.log("TRANSLATION COMPLETED WITH WARNINGS")
            else:
                self.log("TRANSLATION COMPLETED SUCCESSFULLY")
            self.log("============================================================")
            if warnings:
                self.log(f"Warnings: {len(warnings)}")
                for warning in warnings:
                    self.log(f"- {warning}")
                self.log("")
            self.log(f"MO2 ZIP: {result['zip']}")

            if warnings:
                self.root.after(0, lambda: self.progress.configure(mode="determinate", value=100))
                title = t["warning"]
                message = (
                    f"{t['done_warning']}!\n\n"
                    f"Warnings: {len(warnings)}\n\n"
                    f"ZIP:\n{result['zip']}"
                )
                show = messagebox.showwarning
                self.set_status(t["status_warning"])
            else:
                self.root.after(0, lambda: self.progress.configure(mode="determinate", value=100))
                title = t["done"]
                message = f"{t['done']}!\n\nZIP:\n{result['zip']}"
                show = messagebox.showinfo
                self.set_status(t["status_success"])

            self.root.after(0, lambda: show(title, message))

        except Exception as e:
            self.log("")
            self.log("============================================================")
            self.log("TRANSLATION FAILED")
            self.log("============================================================")
            friendly_error = self._friendly_error_message(e)
            self.log(friendly_error)
            self.set_status(t["status_failed"])

            error_title = t["invalid_api_title"] if friendly_error == t["invalid_api"] else t["error"]
            self.root.after(
                0,
                lambda: messagebox.showerror(error_title, friendly_error),
            )

        finally:
            def finish_ui():
                self.progress.stop()
                self.progress.configure(mode="determinate", value=self.progress["value"])
                self.set_translation_controls_enabled(True)
                self.start_button.configure(state="normal")
                self.translation_running = False
            self.root.after(0, finish_ui)

    def load_review_file(self):
        path = filedialog.askopenfilename(
            title="Select translated JSON",
            filetypes=[("JSON Files", "*.json")],
        )

        if not path:
            return

        with open(path, "r", encoding="utf-8") as f:
            self.review_data = json.load(f)

        self.review_path_var.set(path)
        self.review_mode = None

        for child in self.review_tree.get_children():
            self.review_tree.delete(child)

        if isinstance(self.review_data, dict) and "Data" in self.review_data:
            self.review_mode = "archive"

            entries = (
                self.review_data
                .get("Data", {})
                .get("RootChunk", {})
                .get("root", {})
                .get("Data", {})
                .get("entries", [])
            )

            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue

                key = entry.get("secondaryKey", "")
                text = entry.get("femaleVariant", "")

                self.review_tree.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(key, text),
                )
                
        elif isinstance(self.review_data, dict):
            self.review_mode = "flat"

            for key, value in self.review_data.items():
                if isinstance(value, str):
                    self.review_tree.insert(
                        "",
                        "end",
                        iid=str(key),
                        values=(key, value),
                    )

    def on_review_select(self, event=None):
        selection = self.review_tree.selection()
        if not selection:
            return

        item = self.review_tree.item(selection[0])
        values = item.get("values", [])
        
        if len(values) >= 2:
            self.review_edit_var.set(values[1])

    def apply_review_edit(self):
        selection = self.review_tree.selection()
        if not selection or self.review_data is None:
            return

        iid = selection[0]
        new_value = self.review_edit_var.get()
        item = self.review_tree.item(iid)
        key = item["values"][0]

        self.review_tree.item(
            iid,
            values=(key, new_value),
        )

        if self.review_mode == "archive":
            index = int(iid)
            self.review_data["Data"]["RootChunk"]["root"]["Data"]["entries"][index]["femaleVariant"] = new_value
        elif self.review_mode == "flat":
            self.review_data[key] = new_value

    def save_review_file(self):
        path = self.review_path_var.get().strip()
        if not path or self.review_data is None:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                self.review_data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        messagebox.showinfo(
            UI_TEXT[self.current_ui_language]["done"],
            "JSON saved successfully.",
        )

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()