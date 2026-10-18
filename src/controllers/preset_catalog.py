"""Community preset catalog: a moderated list of share codes kept on GitHub.

The catalog lives in its own repository (CATALOG_REPO). Each preset is one
``presets/<id>.json`` file holding a share code plus a title, author and iOS
range; maintainers review every pull request, and a GitHub Actions check
(``tools/preset_catalog.py check``) runs the same validation as this module.
After a merge, ``tools/preset_catalog.py build`` turns the folder into one
``index.json`` that GitHub Pages serves at INDEX_URL.

The app only ever reads that index. Every entry is validated again here and
its share code is decoded locally, so a bad or tampered index can at worst
show fewer presets. Importing an entry stores a preset; it never applies it.
Submitting opens GitHub in the browser with the file already filled in.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote

from PySide6.QtCore import QStandardPaths, QT_TRANSLATE_NOOP

from src.controllers import share_code

CATALOG_REPO = "GoldenNugget-Team/GoldenNugget-Presets"
INDEX_URL = "https://goldennugget-team.github.io/GoldenNugget-Presets/index.json"
REPO_URL = f"https://github.com/{CATALOG_REPO}"
FORMAT_VERSION = 1
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_PRESETS = 2000
MAX_SUBMIT_URL = 7500          # longer prefilled URLs get cut by GitHub or the browser
CACHE_FILENAME = "preset_catalog.json"

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
VERSION_PATTERN = re.compile(r"^\d{1,2}(\.\d{1,2}){0,2}$")
TEXT_LIMITS = {"name": 60, "author": 40, "description": 500}
MAX_TAGS = 8
MAX_TAG_CHARS = 24


class CatalogError(ValueError):
    pass


def version_tuple(version) -> tuple:
    parts = []
    for part in str(version or "").split("."):
        digits = re.match(r"\d+", part)
        parts.append(int(digits.group()) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


@dataclass
class CatalogEntry:
    id: str
    name: str
    author: str
    code: str
    description: str = ""
    ios_min: str = ""
    ios_max: str = ""
    tags: list = field(default_factory=list)
    tweak_count: int = 0

    def supports(self, ios_version) -> bool:
        """True when no iOS range is given or ``ios_version`` is inside it.

        ``ios_max`` "18" covers every 18.x release."""
        if not ios_version:
            return True
        version = version_tuple(ios_version)
        if self.ios_min and version < version_tuple(self.ios_min):
            return False
        if self.ios_max:
            limit = list(version_tuple(self.ios_max))
            depth = len(self.ios_max.split("."))
            if version[:depth] > tuple(limit[:depth]):
                return False
        return True

    def ios_range(self) -> str:
        if self.ios_min and self.ios_max:
            return f"{self.ios_min} – {self.ios_max}"
        if self.ios_min:
            return f"{self.ios_min}+"
        if self.ios_max:
            return f"≤ {self.ios_max}"
        return ""

    def matches(self, text: str) -> bool:
        text = (text or "").strip().casefold()
        if not text:
            return True
        haystack = " ".join([self.name, self.author, self.description, *self.tags]).casefold()
        return all(word in haystack for word in text.split())

    def to_file(self) -> dict:
        data = {"format": FORMAT_VERSION, "name": self.name, "author": self.author,
                "description": self.description, "ios_min": self.ios_min,
                "ios_max": self.ios_max, "tags": list(self.tags), "code": self.code}
        return {key: value for key, value in data.items() if value or key in ("format", "code")}


def _text(raw, key, required=False):
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "A text field has the wrong type."))
    value = " ".join(value.split()) if key != "description" else value.strip()
    if required and not value:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The name and author are required."))
    if len(value) > TEXT_LIMITS[key]:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "A text field is too long."))
    return value


def _version(raw, key):
    value = raw.get(key, "")
    if not isinstance(value, str) or (value and not VERSION_PATTERN.match(value)):
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "iOS versions look like 18 or 18.4."))
    return value


def validate_entry(raw, entry_id: str, validate=None) -> CatalogEntry:
    """Check one catalog file (or index row) and decode its share code.

    ``validate`` is the preset structure check (PresetManager._valid_import_structure)."""
    if not isinstance(raw, dict) or raw.get("format", FORMAT_VERSION) != FORMAT_VERSION:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "Unsupported catalog entry format."))
    if not isinstance(entry_id, str) or not ID_PATTERN.match(entry_id):
        raise CatalogError(QT_TRANSLATE_NOOP(
            "PresetCatalog", "File names use lowercase letters, digits and dashes (2–48 characters)."))
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(
            isinstance(tag, str) and 0 < len(tag.strip()) <= MAX_TAG_CHARS for tag in tags):
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "Up to 8 tags of at most 24 characters."))
    code = raw.get("code")
    if not isinstance(code, str):
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The entry has no share code."))
    entry = CatalogEntry(
        id=entry_id, name=_text(raw, "name", True), author=_text(raw, "author", True),
        description=_text(raw, "description"), code=code.strip(),
        ios_min=_version(raw, "ios_min"), ios_max=_version(raw, "ios_max"),
        tags=[tag.strip().lower() for tag in tags])
    if entry.ios_min and entry.ios_max and version_tuple(entry.ios_min) > version_tuple(entry.ios_max):
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The minimum iOS version is above the maximum."))
    if not entry.code.startswith(share_code.PREFIX) or share_code.extract(entry.code) != entry.code:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The share code must be the whole value."))
    entry.tweak_count = share_code.decode(entry.code, validate)["shared_count"]
    if not entry.tweak_count:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The share code turns on no known tweaks."))
    return entry


def parse_index(data: bytes, validate=None) -> tuple[list, int]:
    """Return (valid entries, number of rejected rows) from index.json bytes."""
    if len(data) > MAX_INDEX_BYTES:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The catalog is too large."))
    try:
        payload = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise CatalogError(QT_TRANSLATE_NOOP("PresetCatalog", "The catalog could not be read.")) from error
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_VERSION \
            or not isinstance(payload.get("presets"), list):
        raise CatalogError(QT_TRANSLATE_NOOP(
            "PresetCatalog", "The catalog needs a newer version of GoldenNugget."))
    entries, rejected, seen = [], 0, set()
    for row in payload["presets"][:MAX_PRESETS]:
        try:
            entry = validate_entry(row, row.get("id") if isinstance(row, dict) else None, validate)
        except (CatalogError, share_code.ShareCodeError):
            rejected += 1
            continue
        if entry.id in seen:
            rejected += 1
            continue
        seen.add(entry.id)
        entries.append(entry)
    return entries, rejected


def build_index(entries, generated=None) -> dict:
    rows = []
    for entry in sorted(entries, key=lambda item: item.name.casefold()):
        row = entry.to_file()
        row["id"] = entry.id
        rows.append(row)
    return {"format": FORMAT_VERSION, "generated": int(generated if generated is not None else time.time()),
            "presets": rows}


# --- local cache ----------------------------------------------------------

def cache_path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation) \
        or QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, CACHE_FILENAME)


def read_cache():
    """(bytes, saved_at) of the last good index, or (None, 0)."""
    try:
        path = cache_path()
        with open(path, "rb") as file:
            return file.read(MAX_INDEX_BYTES + 1), os.path.getmtime(path)
    except OSError:
        return None, 0


def write_cache(data: bytes):
    try:
        with open(cache_path(), "wb") as file:
            file.write(data)
    except OSError:
        pass


# --- submitting -----------------------------------------------------------

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").casefold()).strip("-")[:48].strip("-")
    return slug if ID_PATTERN.match(slug) else "preset-" + time.strftime("%Y%m%d%H%M%S")


def submission(name, author, code, description="", ios_min="", ios_max="", tags=(), validate=None):
    """Validated (file name, file text) for a new catalog entry."""
    raw = {"format": FORMAT_VERSION, "name": name, "author": author, "description": description,
           "ios_min": ios_min, "ios_max": ios_max, "code": code,
           "tags": [tag.strip() for tag in tags if tag.strip()]}
    entry = validate_entry(raw, slugify(name), validate)
    text = json.dumps(entry.to_file(), ensure_ascii=False, indent=2) + "\n"
    return f"{entry.id}.json", text


def submit_url(filename: str, text: str) -> tuple[str, bool]:
    """GitHub "new file" page for the catalog; (url, prefilled).

    GitHub forks the repository and opens a pull request for people without
    write access. When the file is too long for a URL, only the name is
    filled in and the caller puts the text on the clipboard instead."""
    base = f"{REPO_URL}/new/main/presets?filename={quote(filename)}"
    url = f"{base}&value={quote(text, safe='')}"
    if len(url) <= MAX_SUBMIT_URL:
        return url, True
    return base, False
