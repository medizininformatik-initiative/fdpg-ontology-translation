import argparse
import logging
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from fhir.resources.R4B.valueset import ValueSet

from TerminologyClient import TerminologyClient
from Translator import Translator
from TranslatorEngine import (
    DeeplTranslationEngine,
    DryRunTranslationEngine,
    TranslationEngine,
)
from ValueSetManager import ValueSetManager

logger = logging.getLogger(__name__)


def configure_args_parser():
    arg_parser = argparse.ArgumentParser(
        description="Generate Translations for fdpg terms"
    )
    arg_parser.add_argument(
        "--target_folder",
        type=str,
        help="Folder to output the translated files to",
        nargs="?",
        default="code-systems",
    )
    arg_parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Do not translate, count the characters to be translated",
    )
    arg_parser.add_argument(
        "--deepl",
        action="store_true",
        help="Translate with deepl",
    )
    arg_parser.add_argument(
        "--package_cache",
        type=str,
        help="FHIR package cache folder with the ValueSets to translate",
        default=None,
    )
    arg_parser.add_argument(
        "--input_folder",
        type=str,
        help="Optional folder with additional ValueSet JSON files to translate (used together with the package cache)",
        default=None,
    )

    return arg_parser


def configure_logging(log_level_arg):
    log_level = {
        "notset": 0,
        "debug": 10,
        "info": 20,
        "warning": 30,
        "error": 40,
        "critical": 50,
    }
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=log_level[log_level_arg],
    )
    logging.getLogger("deepl").disabled = True


if __name__ == "__main__":
    load_dotenv()
    args = configure_args_parser().parse_args()
    configure_logging(os.getenv("LOG_LEVEL"))

    if args.package_cache is None and args.input_folder is None:
        logger.warning(
            "No input provided: use --package_cache and/or --input_folder to specify the ValueSets to translate"
        )
        sys.exit(1)

    session = requests.Session()
    session.cert = (os.getenv("SERVER_CERTIFICATE"), os.getenv("PRIVATE_KEY"))
    terminology_client = TerminologyClient(
        session, os.getenv("TERMINOLOGY_SERVER"), os.getenv("BACKUP_TERMINOLOGY_SERVER")
    )

    vsm = ValueSetManager(
        package_cache_folder=Path(args.package_cache) if args.package_cache else None,
        ingest_folder=Path(args.input_folder) if args.input_folder else None,
        terminology_client=terminology_client,
    )

    # DeepL only on explicit request; dry run is the default
    translation_engine: TranslationEngine = (
        DeeplTranslationEngine(os.getenv("DEEPL_API_KEY"), source_langs=["de", "en"])
        if args.deepl and not args.dry_run
        else DryRunTranslationEngine(source_langs=["de", "en"])
    )
    logger.info(f"Translation engine: {type(translation_engine).__name__}")
    translator = Translator(
        translation_engine=translation_engine,
        terminology_client=terminology_client,
        target_langs=["de", "en"],
    )

    # collect codes from expanded valuesets
    for value_set in vsm.local_index.values():
        value_set: ValueSet
        translator.collect_codes_from_value_set(value_set)

    # download codesystem translations supplements from server
    translator.build_cache_from_existing_supplements_bundle()
    translator.translate()
    translator.export_codesystem_supplements(Path(args.target_folder))

    logger.info(f"translated: {translation_engine.get_character_count()}")
