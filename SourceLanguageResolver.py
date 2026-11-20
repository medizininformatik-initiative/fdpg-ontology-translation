import json
import logging
from pathlib import Path

from lingua import IsoCode639_1, LanguageDetectorBuilder

logger = logging.getLogger(__name__)


SYSTEM_PREFIX_LANG = {
    "http://fhir.de/": "de",
    "http://terminology.hl7.org/": "en",
    "http://hl7.org/fhir/": "en",
    "http://snomed.info/sct": "en",
    "http://loinc.org": "en",
}


class SourceLanguageResolver:
    def __init__(self, languages: list[str]):
        self._cache: dict[str, str | None] = {}

        iso_codes = []
        for code in languages:
            iso_code = getattr(IsoCode639_1, code.upper(), None)
            if iso_code is None:
                logger.warning(
                    f"Language '{code}' is not supported by lingua, skipping"
                )
                continue
            iso_codes.append(iso_code)

        if len(iso_codes) < 2:
            raise ValueError("Lingua needs at least two languages to detect between")

        self._detector = LanguageDetectorBuilder.from_iso_codes_639_1(
            *iso_codes
        ).build()

    def resolve(self, system: str, sample_displays: list[str]) -> str | None:
        if system not in self._cache:
            self._cache[system] = self._from_prefix(system) or self._detect(
                sample_displays
            )
        return self._cache[system]

    def _from_prefix(self, system: str) -> str | None:
        return next(
            (
                lang
                for prefix, lang in SYSTEM_PREFIX_LANG.items()
                if system.startswith(prefix)
            ),
            None,
        )

    def _detect(self, displays: list[str]) -> str | None:
        language = self._detector.detect_language_of(". ".join(displays[:10]))
        return language.iso_code_639_1.name.lower() if language else None

    def _dump_cache(self, path: Path):
        path.write_text(json.dumps(self._cache))
