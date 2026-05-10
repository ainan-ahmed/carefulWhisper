"""
Post-processing pipeline applied to raw STT output.
Handles punctuation, capitalization, custom vocab substitutions,
filler word removal, number formatting, unicode cleanup, and self-corrections.
"""

from __future__ import annotations

import re

from backend.config import PostProcessConfig


class PostProcessor:
    def __init__(self, cfg: PostProcessConfig) -> None:
        self.cfg = cfg
        self._subs: list[tuple[re.Pattern, str]] = [
            (re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE), v)
            for k, v in cfg.substitutions.items()
        ]
        if cfg.filler_words:
            filler_alt = "|".join(re.escape(w) for w in cfg.filler_words)
            self._filler_re = re.compile(
                r"\b(?:" + filler_alt + r")\b", re.IGNORECASE
            )
        else:
            self._filler_re = None

        self._correction_patterns: list[re.Pattern] = [
            re.compile(
                r"(.+?)\s+[-–—]+\s+(?:i mean|actually|wait|no|sorry|rather)\s+(.+)",
                re.IGNORECASE,
            ),
            re.compile(r"(.+?)\s+or rather\s+(.+)", re.IGNORECASE),
            re.compile(
                r"(.+?)\s+(?:actually\s+)?(?:wait|no),?\s+(.+)", re.IGNORECASE
            ),
        ]

    def process(self, text: str) -> str:
        if not text:
            return text

        if self.cfg.fix_unicode:
            text = self._fix_unicode(text)

        text = self._apply_substitutions(text)

        if self.cfg.remove_fillers:
            text = self._remove_fillers(text)

        if self.cfg.handle_self_corrections:
            text = self._handle_self_corrections(text)

        if self.cfg.format_numbers:
            text = self._format_numbers(text)

        if self.cfg.fix_punctuation:
            text = self._fix_punctuation(text)

        if self.cfg.capitalize_sentences:
            text = self._capitalize_sentences(text)

        return text.strip()

    def _fix_unicode(self, text: str) -> str:
        import ftfy  # type: ignore[import]

        return ftfy.fix_text(text)

    def _apply_substitutions(self, text: str) -> str:
        for pattern, replacement in self._subs:
            text = pattern.sub(replacement, text)
        return text

    def _remove_fillers(self, text: str) -> str:
        if self._filler_re is None:
            return text
        text = self._filler_re.sub("", text)
        return text

    def _handle_self_corrections(self, text: str) -> str:
        for pattern in self._correction_patterns:
            match = pattern.search(text)
            if match:
                text = match.group(2).strip()
                break
        return text

    def _format_numbers(self, text: str) -> str:
        from text_to_num import alpha2digit  # type: ignore[import]

        return alpha2digit(text, lang="en")

    _TLDs = frozenset({
        "com", "org", "net", "io", "edu", "gov", "ai", "app", "dev",
        "co", "uk", "us", "ca", "de", "fr", "jp", "au", "in", "ru",
        "info", "biz", "me", "tv", "cc", "xyz", "online", "tech",
        "cloud", "site", "store", "pro", "mobi", "name", "mil", "int",
    })

    def _fix_punctuation(self, text: str) -> str:
        text = re.sub(r" {2,}", " ", text)

        def _space_after(m: re.Match) -> str:
            punct = m.group(1)
            after_char = m.group(2)
            if punct == ".":
                before_text = text[: m.start()]
                word_before = re.search(r"(\w+)$", before_text)
                if word_before and word_before.group(1).lower() in self._TLDs:
                    return m.group(0)
                
                after_text = text[m.end() - 1 :]
                word_after = re.match(r"([A-Za-z]+)", after_text)
                if word_after:
                    w_lower = word_after.group(1).lower()
                    if w_lower in self._TLDs or w_lower in {"txt", "zip", "png", "jpg", "jpeg", "gif", "mp3", "wav", "mp4", "pdf", "html", "svg", "webp"}:
                        return m.group(0)
            return punct + " " + after_char

        text = re.sub(r"([.!?])([A-Za-z])", _space_after, text)
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        return text

    def _capitalize_sentences(self, text: str) -> str:
        def _replacer(m: re.Match) -> str:
            punct = m.group(1)
            space = m.group(2)
            char = m.group(3)
            if punct == ".":
                before_text = text[: m.start()]
                word_before = re.search(r"(\w+)$", before_text)
                if word_before and word_before.group(1).lower() in self._TLDs:
                    return m.group(0)
                
                after_text = text[m.end() - 1 :]
                word_after = re.match(r"([a-z]+)", after_text, re.IGNORECASE)
                if word_after:
                    w_lower = word_after.group(1).lower()
                    if w_lower in self._TLDs or w_lower in {"txt", "zip", "png", "jpg", "jpeg", "gif", "mp3", "wav", "mp4", "pdf", "html", "svg", "webp"}:
                        return m.group(0)
            return punct + space + char.upper()

        return re.sub(r"([.!?])(\s+)([a-z])", _replacer, text)
