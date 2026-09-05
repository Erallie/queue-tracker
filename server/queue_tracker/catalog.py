from __future__ import annotations

import re
from dataclasses import dataclass

NEW_RE = re.compile(r"\s*\[New\]\s*$", re.IGNORECASE)
PAREN_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


@dataclass(frozen=True)
class ParsedSong:
    raw_title: str
    title: str
    parenthetical: str
    section: str
    is_new: bool


def split_name(value: str) -> tuple[str, str]:
    clean = NEW_RE.sub("", value).strip()
    match = PAREN_RE.match(clean)
    if not match:
        return clean, ""
    return match.group(1).strip(), match.group(2).strip()


def parse_song_text(text: str) -> list[ParsedSong]:
    songs: list[ParsedSong] = []
    started = False
    section = ""
    for source_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = source_line.strip()
        if not started:
            if line.startswith("#"):
                started = True
            else:
                continue
        if not line or line.startswith("*"):
            continue
        if line.startswith("#"):
            if line.startswith("# "):
                section = line[2:].strip()
            continue
        is_new = bool(NEW_RE.search(line))
        raw = NEW_RE.sub("", line).strip()
        title, parenthetical = split_name(raw)
        if raw:
            songs.append(ParsedSong(raw, title, parenthetical, section, is_new))
    return songs


def remove_new_marker(text: str, raw_titles: set[str]) -> str:
    result: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        clean = NEW_RE.sub("", line).strip()
        result.append(NEW_RE.sub("", line).rstrip() if clean in raw_titles else line)
    return "\n".join(result)


def add_new_marker(text: str, raw_titles: set[str]) -> str:
    result: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        clean = NEW_RE.sub("", line).strip()
        if clean in raw_titles and not NEW_RE.search(line):
            result.append(f"{line.rstrip()} [New]")
        else:
            result.append(line)
    return "\n".join(result)
