import logging
from abc import ABC, abstractmethod
from collections import Counter

import deepl

from SourceLanguageResolver import SourceLanguageResolver

logger = logging.getLogger(__name__)


class TranslationEngine(ABC):
    """
    Translates texts into the demanded target languages.
    The source language is handled entirely inside the engine:
    a local guess (prefix rules / lingua, cached per system), corrected by what the engine detects.
    """

    def __init__(self, source_langs: list[str] = ("de", "en")):
        self.source_langs = list(source_langs)
        self.source_lang_resolver = SourceLanguageResolver(self.source_langs)

    def translate(
        self,
        system: str,
        texts_by_lang: dict[str, list[str]],
        context: str | None = None,
    ) -> dict[str, list[str]]:
        """
        :param system: code system the texts belong to (one source language per system)
        :param texts_by_lang: target language -> texts that need that language
        :return: target language -> translations, in the same order
        """
        sample = max(texts_by_lang.values(), key=len)
        source_lang = self.source_lang_resolver.resolve(system, sample[:10])

        result: dict[str, list[str]] = {}
        # the guessed source language goes last: if a different source language is detected
        # on the way, the guess is no longer skipped but translated
        for target_lang in sorted(texts_by_lang, key=lambda l: l == source_lang):
            texts = texts_by_lang[target_lang]
            if not texts or target_lang == source_lang:
                result[target_lang] = list(
                    texts
                )  # source language needs no translation
                continue

            result[target_lang], detected = self._translate(
                texts, target_lang, source_lang, context
            )

            if detected in self.source_langs and detected != source_lang:
                logger.warning(
                    f"{system}: detected '{detected}', local guess was '{source_lang}'"
                )
                source_lang = detected
        return result

    @abstractmethod
    def _translate(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: str | None,
        context: str | None = None,
    ) -> tuple[list[str], str | None]:
        """Translate into one language. Returns the translations and the detected source language."""

    @abstractmethod
    def get_character_count(self) -> int:
        pass

    # @abstractmethod
    # def translate_code(self, concept: ConceptTriplet, target_lang, context):
    #     pass


class DeeplTranslationEngine(TranslationEngine):
    MAX_TEXTS_PER_REQUEST = 50  # DeepL limit per request
    DETECTION_BATCH_SIZE = 20  # first batch, used to detect the source language

    def __init__(
        self,
        deepl_key: str,
        batch_size: int = MAX_TEXTS_PER_REQUEST,
        source_langs: list[str] = ("de", "en"),
    ):
        super().__init__(source_langs)
        self._client = deepl.Translator(deepl_key)
        self.batch_size = min(batch_size, self.MAX_TEXTS_PER_REQUEST)
        self.characters = 0

    def _translate(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: str | None,
        context: str | None = None,
    ) -> tuple[list[str], str | None]:
        """
        Translate texts, preserving order.
        DeepL detects the source language on a small first batch (the local guess in
        source_lang is not needed for that); the rest is sent with the detected language.
        """
        if not texts:
            return [], None

        # 1. first batch without source language: DeepL detects it
        first = texts[: self.DETECTION_BATCH_SIZE]
        translated = self._translate_chunk(first, target_lang, None, context)
        detected = Counter(lang for _, lang in translated).most_common(1)[0][0]

        # 2. texts are already in the target language: no further requests
        if detected == target_lang.lower():
            return list(texts), detected

        # 3. rest with the detected source language
        rest = texts[len(first) :]
        for start in range(0, len(rest), self.batch_size):
            chunk = rest[start : start + self.batch_size]
            translated += self._translate_chunk(chunk, target_lang, detected, context)
        return [text for text, _ in translated], detected

    def _translate_chunk(
        self,
        chunk: list[str],
        target_lang: str,
        source_lang: str | None,
        context: str | None,
    ) -> list[tuple[str, str]]:
        """One DeepL request. Returns (translation, detected source language) per text."""
        results = self._client.translate_text(
            chunk,
            source_lang=self._to_deepl_source(source_lang),
            target_lang=self._to_deepl_target(target_lang),
            context=context,
        )
        self.characters += sum(
            len(t) for t in chunk
        )  # DeepL bills the source characters
        return [(r.text, r.detected_source_lang.lower()) for r in results]

    @staticmethod
    def _to_deepl_source(lang: str | None) -> str | None:
        # source languages have no regional variants: "en" → "EN"
        return lang.upper() if lang else None

    @staticmethod
    def _to_deepl_target(lang: str) -> str:
        # plain "EN" is deprecated as a target, DeepL wants a variant
        return {"en": "EN-US"}.get(lang.lower(), lang.upper())

    def get_character_count(self) -> int:
        return self.characters


class DryRunTranslationEngine(TranslationEngine):
    def __init__(self, source_langs: list[str] = ("de", "en")):
        super().__init__(source_langs)
        self.characters = 0

    def _translate(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: str | None,
        context: str | None = None,
    ) -> tuple[list[str], str | None]:
        # no detection: the local guess is taken as correct
        self.characters += sum(len(x) for x in texts)
        return list(texts), source_lang

    def get_character_count(self) -> int:
        return self.characters


# class LLMTranslationsEngine(TranslationEngine):
#     def translate_batch(
#         self, codes: list[ConceptTriplet], target_lang: str, context: str, batch_size:int = 5
#     ):
#         pass
