import argparse
import json
import logging
import os
import sys

import deepl

logger = logging.getLogger(__name__)

def configure_args_parser():
    arg_parser = argparse.ArgumentParser(description="Generate Translations for fdpg terms")
    arg_parser.add_argument("--value_sets_folder", type=str, help="Folder with value-sets to be listed in json",
                            nargs="?", default="value-sets")
    arg_parser.add_argument("--log_level", type=str, help="notset|debug|info|warning|error|critical", nargs="?",
                            default="info")
    arg_parser.add_argument("--deepl_api_key", type=str, help="deepl api key")
    arg_parser.add_argument("--lang_detection", action='store_true', help="without language detection")

    return arg_parser


def configure_logging(log_level_arg):
    log_level = {
        "notset": 0,
        "debug": 10,
        "info": 20,
        "warning": 30,
        "error": 40,
        "critical": 50
    }
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=log_level[log_level_arg],
    )
    logging.getLogger("deepl").disabled = True


if __name__ == "__main__":
    args = configure_args_parser().parse_args()
    configure_logging(args.log_level)

    deepl_engine = deepl.Translator(args.deepl_api_key)
    folder_path = args.value_sets_folder

    try:
        # List all files in the directory
        files = []
        for f in os.listdir(folder_path):
            if os.path.isfile(os.path.join(folder_path, f)) and f.endswith(".json"):

                source_lang = "de"
                if args.lang_detection:
                    with open(os.path.join(folder_path, f), "r", encoding="utf-8") as json_file:
                        json_data = json.load(json_file)
                        value_set_sample = json_data["expansion"]["contains"][0]["display"]
                    result = deepl_engine.translate_text(text=value_set_sample, target_lang="DE")
                    logger.info(value_set_sample + " -> source: " + result.detected_source_lang)
                    source_lang = result.detected_source_lang

                files.append({
                    "url": os.path.join(folder_path, f),
                    "source_lang": source_lang
                })

        with open("valueSets.default.json", "w", encoding="utf-8") as file:
            json.dump(files, file, ensure_ascii=False)
    except Exception as e:
        logging.error(e)
