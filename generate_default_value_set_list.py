import argparse
import json
import logging
import os
import sys


def configure_args_parser():
    arg_parser = argparse.ArgumentParser(description="Generate Translations for fdpg terms")
    arg_parser.add_argument("--value_sets_folder", type=str, help="Folder with value-sets to be listed in json",nargs="?",default="value-sets")
    arg_parser.add_argument("--log_level", type=str, help="notset|debug|info|warning|error|critical", nargs="?",
                            default="info")

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

    folder_path = args.value_sets_folder

    try:
        # List all files in the directory
        files = []
        for f in os.listdir(folder_path):
            if os.path.isfile(os.path.join(folder_path, f)) and f.endswith(".json"):
                files.append({
                    "url": os.path.join(folder_path, f),
                    "source_lang": "de"
                })

        with open("valueSets.default.json", "w", encoding="utf-8") as file:
            json.dump(files, file, ensure_ascii=False)
    except Exception as e:
        logging.error(e)