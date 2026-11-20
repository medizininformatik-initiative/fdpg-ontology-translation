import logging
import re
from pathlib import Path

from fhir.resources.R4B.bundle import Bundle, BundleEntry
from fhir.resources.R4B.codesystem import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
)
from fhir.resources.R4B.valueset import ValueSet, ValueSetExpansionContains

from models import ConceptTriplet, TripletKey
from TerminologyClient import TerminologyClient
from TranslatorEngine import TranslationEngine

logger = logging.getLogger(__name__)

# project tag the termserver sets on every FDPG resource
FDPG_PROJECT_TAG = (
    "https://mii-termserv.de/fhir/su-termserv/CodeSystem/mii-cs-suts-resource-tags-project",
    "fdpg",
)


def has_tag(resource, tag: tuple[str, str]) -> bool:
    tags = resource.meta.tag if resource.meta and resource.meta.tag else []
    return any((t.system, t.code) == tag for t in tags)


class Translator:
    def __init__(
        self,
        translation_engine: TranslationEngine,
        terminology_client: TerminologyClient,
        target_langs: list[str],
    ):
        self.value_set: ValueSet | None
        self.code_systems: list[CodeSystem]
        self.translation_engine: TranslationEngine = translation_engine
        self.terminology_client: TerminologyClient = terminology_client
        self.target_langs: list[str] = target_langs

        # codesystem, codesystem_version
        # codes get loaded into the following structure, then translated by codesystem in batches
        self.concept_translations: dict[
            tuple[str, str | None], dict[TripletKey, ConceptTriplet]
        ] = {}

        # translated concepts get output into this structure
        # self.concepts_translated: dict[
        #     tuple[str, str | None], dict[TripletKey, ConceptTriplet]
        # ] = {}

    def _enqueue(self, triplet: ConceptTriplet) -> None:
        codesystem_ident = (triplet.system, triplet.version)
        codesystem = self.concept_translations.get(codesystem_ident)
        existing = codesystem.get(triplet.key) if codesystem else None

        if codesystem is None:
            self.concept_translations[codesystem_ident] = {}

        if existing is None:
            self.concept_translations[codesystem_ident][triplet.key] = triplet
            return

    def collect_codes_from_value_set(self, valueSet: ValueSet):
        """

        :param valueSet:
        :return:
        """
        if valueSet.expansion is None or valueSet.expansion.contains is None:
            logger.error(
                f"ValueSet {valueSet.url} with version {valueSet.version} needs to be expanded"
            )
            return

        for concept in valueSet.expansion.contains:
            concept: ValueSetExpansionContains
            if not all([concept.code, concept.system, concept.display]):
                logger.error(
                    f"Code {concept.code} has no url: {concept.system} or display: {concept.display}"
                )
                continue

            self._enqueue(
                ConceptTriplet(
                    code=concept.code,
                    system=concept.system,
                    version=concept.version,
                    original_display=concept.display,
                )
            )

    def translate(self):
        """
        Translate batch of codes from the same codesystem.
        It needs to be the same to be able to reliably detect the codesystems source lang
        :return:
        """
        for (system, version), codesystem in self.concept_translations.items():
            # per target language: only codes without a translation yet (e.g. from a supplement)
            todo = {
                lang: [v for v in codesystem.values() if lang not in v.display]
                for lang in self.target_langs
            }

            # the engine handles the source language itself
            translated = self.translation_engine.translate(
                system=system,
                texts_by_lang={
                    lang: [v.original_display for v in vs] for lang, vs in todo.items()
                },
                context=". ".join(
                    v.original_display for v in list(codesystem.values())[:50]
                ),  # TBD
            )

            for lang, vs in todo.items():
                for v, t in zip(vs, translated[lang], strict=True):
                    v.display[lang] = t

    def build_cache_from_existing_supplements_bundle(self):
        suplements_bundle: Bundle | None = (
            self.terminology_client.fetch_existing_supplements()
        )
        if not suplements_bundle:
            return

        for entry in suplements_bundle.entry or []:
            entry: BundleEntry
            # only FDPG supplements; checked on the header so others are never downloaded
            if not has_tag(entry.resource, FDPG_PROJECT_TAG):
                continue
            found = self.terminology_client.get_code_system(id=entry.resource.id)
            if not found or not found[0].supplements:
                continue
            css: CodeSystem = found[0]

            # the base system is in "supplements" ("url|version"), not in css.url.
            # The version is ignored; instead a translation is only applied
            # if the supplement still contains the queued original source text
            system = css.supplements.partition("|")[0]
            queued_groups = [
                (ver, group)
                for (sys, ver), group in self.concept_translations.items()
                if sys == system
            ]

            # only codes that are already queued from the ValueSets get the designations
            for concept in css.concept or []:
                for ver, group in queued_groups:
                    triplet = group.get((concept.code, system, ver))
                    designations = concept.designation or []
                    # source text changed between versions -> translate again
                    if triplet is None or triplet.original_display not in [
                        d.value for d in designations
                    ]:
                        continue
                    for designation in designations:
                        # de-DE => de
                        triplet.display[designation.language.split("-")[0]] = (
                            designation.value
                        )

    def export_codesystem_supplements(self, output_folder: Path):
        output_folder.mkdir(exist_ok=True)

        for (system, version), concepts in self.concept_translations.items():
            # key from the last part of system and version, e.g. "alpha_id_2025", "sct_20240701"
            short = lambda s: re.split(r"[/:]", s.rstrip("/"))[-1]
            key = re.sub(
                r"[^A-Za-z0-9]+",
                "_",
                f"{short(system)}_{short(version)}" if version else short(system),
            ).strip("_")
            # FHIR name: [A-Z][A-Za-z0-9_]*
            name = f"{key[0].upper()}{key[1:]}" if key[0].isalpha() else f"CS_{key}"

            # same conventions as the FDPG supplements already on the server
            codesystem_out: CodeSystem = CodeSystem(
                url=f"https://fdpg.de/fhir/CodeSystem/{key}/translations",
                version="1.0.0",
                name=f"{name}_FDPG_Translation_Supplement",
                status="active",  # required
                content="supplement",  # required
                supplements=f"{system}|{version}" if version else system,
                concept=[
                    CodeSystemConcept(
                        code=concept_triplet.code,
                        designation=[
                            CodeSystemConceptDesignation(language=k, value=v)
                            for k, v in concept_triplet.display.items()
                        ],
                        display=concept_triplet.original_display,
                    )
                    for concept_triplet in concepts.values()
                ],
                count=len(concepts),
            )

            out_file = output_folder / f"{key}.json"
            out_file.write_text(
                codesystem_out.model_dump_json(indent=2), encoding="utf-8"
            )

            logger.info(f"Translated {system}|{version}. Saved at {out_file}")
