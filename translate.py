import argparse
import json
import requests
import logging
import sys

from Translator import Translator

logger = logging.getLogger(__name__)


def configure_args_parser():
    arg_parser = argparse.ArgumentParser(description="Generate Translations for fdpg terms")
    arg_parser.add_argument("--terminology_server", type=str, help="The terminology server address")
    arg_parser.add_argument("--server_certificate", type=str, help="The server certificate")
    arg_parser.add_argument("--private_key", type=str, help="The private key")
    arg_parser.add_argument("--deepl_api_key", type=str, help="The DeepL API key")
    arg_parser.add_argument("--value_sets", type=str, help="File with the urls and languages")
    arg_parser.add_argument("--target_folder",type=str,help="Folder to output the translated files to",nargs="?",default="code-systems")
    arg_parser.add_argument("--log_level",type=str,help="notset|debug|info|warning|error|critical",nargs="?",default="info")
    arg_parser.add_argument("--batch_size",type=int,help="Integer specifying the count of elements sent simultaneously",nargs="?",default="3")
    arg_parser.add_argument('--dry_run', action='store_true', help='Do not translate, only count number of characters that would be translated')

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

    session = requests.Session()
    session.cert = (args.server_certificate, args.private_key)

    value_sets = json.load(open(args.value_sets, "r", encoding="utf-8"))
    translator = Translator(args.deepl_api_key, session, args.terminology_server, ["de", "en"])
    nr_of_translated_files = 0
    characters_translated = 0

    for value_set in value_sets:

        chars_translated = translator.translate(value_set["url"], value_set["source_lang"], args.dry_run, batch_size=args.batch_size)

        if chars_translated > 0:
            logger.info(f"ValueSet: {value_set['url']} contains characters: {chars_translated}")
            characters_translated = characters_translated + chars_translated
            translator.save(target_folder=args.target_folder)
            nr_of_translated_files += 1

    logger.info("Total: %s files",nr_of_translated_files)
    logger.info(f"Total: {characters_translated:,} characters translated")
