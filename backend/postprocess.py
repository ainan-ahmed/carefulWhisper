"""
Post-processing pipeline applied to raw STT output.
Handles punctuation, capitalization, custom vocab substitutions,
filler word removal, number formatting, unicode cleanup, and self-corrections.
"""

from __future__ import annotations

import re

from backend.config import PostProcessConfig
from backend.config import LLMConfig


class PostProcessor:
    def __init__(self, cfg: PostProcessConfig, llm_cfg: LLMConfig | None = None) -> None:
        self.cfg = cfg
        self.llm_cfg = llm_cfg or LLMConfig()
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

    def process(self, text: str) -> tuple[str, str]:
        if not text:
            return "stt", text

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

        mode = "stt"
        if self.llm_cfg.enabled:
            mode, text = self._apply_llm(text)

        return mode, text.strip()

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
        def _cap(match: re.Match) -> str:
            prefix = match.group(1)
            letter = match.group(2)
            return f"{prefix}{letter.upper()}"

        return re.sub(r"(^|[.!?]\s+)([a-z])", _cap, text)

    def _cleanup_llm_text(self, text: str | None) -> str:
        if not text:
            return ""
        text = text.strip()
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _apply_llm(self, text: str) -> tuple[str, str]:
        import logging
        logger = logging.getLogger("carefulwhisper.postprocess")
        
        trigger_phrase = (self.llm_cfg.trigger_phrase or "").strip()
        has_trigger = False
        clean_text = text
        if trigger_phrase:
            # Look for a fuzzy trigger phrase within the last N words to reduce false positives.
            window_words = 12
            word_spans = [m.span() for m in re.finditer(r"\b\w+\b", text)]
            start_idx = word_spans[-window_words][0] if len(word_spans) >= window_words else 0
            tail = text[start_idx:]

            variants = [trigger_phrase]
            if trigger_phrase.lower() == "fixnow":
                variants.extend(["fix now", "fix no", "fix so", "fix new"])

            for variant in variants:
                trigger_re = re.compile(r"\b" + re.escape(variant) + r"\b", re.IGNORECASE)
                match = trigger_re.search(tail)
                if match:
                    has_trigger = True
                    logger.debug("LLM trigger matched variant '%s' in tail window", variant)
                    cleaned_tail = trigger_re.sub("", tail, count=1)
                    clean_text = (text[:start_idx] + cleaned_tail).strip()
                    break

        if not has_trigger:
            mode = getattr(self.llm_cfg, "mode", "stt")
            if mode != "auto" and mode != "assistant":
                if not self.llm_cfg.auto_on_length_enabled:
                    return "stt", text
                clean_len = len(clean_text)
                logger.debug("LLM auto-length check: len=%s threshold=%s", clean_len, self.llm_cfg.auto_on_length_threshold)
                if clean_len < self.llm_cfg.auto_on_length_threshold:
                    return "stt", text
                logger.debug("LLM auto-length trigger fired")
        try:
            from pydantic_ai import Agent

            mode = getattr(self.llm_cfg, "mode", "stt")
            if mode == "auto":
                router_model = getattr(self.llm_cfg, "router_model", "gemini-2.5-flash")
                if router_model.startswith("gemini"):
                    router_model = f"google:{router_model}"
                router_agent = Agent(
                    router_model,
                    system_prompt=(
                        "You are a dual-mode intent classifier for a voice app. Classify the user's input.\n"
                        "- Output COMMAND if the user is asking a question, requesting a task, or prompting an AI (e.g., 'Write a python script', 'What's the weather?', 'Summarize this').\n"
                        "- Output DICTATION if the user is dictating text for an email, document, or general transcription (e.g., 'Dear John, I will be late.', 'Note for the meeting:').\n"
                        "Output STRICTLY 'COMMAND' or 'DICTATION'."
                    )
                )
                route_res = router_agent.run_sync(clean_text)
                decision = route_res.output.strip().upper()
                logger.debug("LLM router decision: %s", decision)
                if "COMMAND" in decision or "ASSISTANT" in decision:
                    mode = "assistant"
                else:
                    mode = "stt"

            if mode == "assistant":
                sys_prompt = getattr(self.llm_cfg, "assistant_prompt", "You are a helpful AI assistant. Answer the user's question or command concisely.")
                user_prompt = clean_text
            else:
                sys_prompt = self.llm_cfg.system_prompt
                user_prompt = self.llm_cfg.prompt.replace("{text}", clean_text)

            model_name = self.llm_cfg.model
            if model_name.startswith("gemini"):
                model_name = f"google:{model_name}"
            agent = Agent(model_name, system_prompt=sys_prompt)
            result = agent.run_sync(user_prompt)
            enhanced_text = result.output

            if mode == "stt":
                enhanced_text = self._cleanup_llm_text(enhanced_text)
            else:
                enhanced_text = enhanced_text.strip()
                
            logger.debug("LLM enhanced text: %s", enhanced_text)
            return mode, enhanced_text
        except Exception as e:
            logger.exception("LLM enhancement failed")
            return "stt", text
