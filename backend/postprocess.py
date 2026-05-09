"""
Post-processing pipeline applied to raw STT output.
Handles punctuation, capitalization, custom vocab substitutions.
"""

from __future__ import annotations

import re

from backend.config import PostProcessConfig


class PostProcessor:
    def __init__(self, cfg: PostProcessConfig) -> None:
        self.cfg = cfg
        # Pre-compile substitution patterns for speed
        self._subs: list[tuple[re.Pattern, str]] = [
            (re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE), v)
            for k, v in cfg.substitutions.items()
        ]

    def process(self, text: str) -> str:
        if not text:
            return text

        text = self._apply_substitutions(text)

        if self.cfg.fix_punctuation:
            text = self._fix_punctuation(text)

        if self.cfg.capitalize_sentences:
            text = self._capitalize_sentences(text)

        return text.strip()

    def _apply_substitutions(self, text: str) -> str:
        for pattern, replacement in self._subs:
            text = pattern.sub(replacement, text)
        return text

    def _fix_punctuation(self, text: str) -> str:
        # Remove double spaces
        text = re.sub(r" {2,}", " ", text)
        # Ensure space after sentence-ending punctuation
        text = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)
        # Remove space before punctuation
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        return text

    def _capitalize_sentences(self, text: str) -> str:
        # Capitalize after sentence boundaries and at start
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(s[0].upper() + s[1:] if s else s for s in sentences)
