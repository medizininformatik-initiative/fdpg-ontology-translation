import json
import os
from urllib.parse import urlparse
import logging
import deepl

logger = logging.getLogger(__name__)


class Translator:
    def __init__(
            self, deepl_auth_key, session, terminology_server_address, target_langs
    ):
        self.value_set = None
        self.code_system_template = None
        self.code_system_version = None
        self.code_system_url = None
        self.code_system_name = None
        self.deepl_engine = deepl.Translator(deepl_auth_key)
        self.session = session
        self.terminology_server_address = terminology_server_address
        self.target_langs = target_langs

    def get_code_system_url(self):
        for param in self.value_set["expansion"]["parameter"]:
            if param["name"] == "used-codesystem":
                return param["valueUri"]

    def get_code_system_name(self):
        return self.value_set.get(
            "name",
            urlparse(self.value_set.get("url"))
            .path.split("/ValueSet/", 1)[-1]
            .replace("/", ""),
        )

    def get_value_sets(self, value_set_url):
        try:
            with open(value_set_url, "r", encoding="utf-8") as file:
                return json.load(file)
        except IOError:
            logger.info("%s not found among files locally, downloading instead ... ", value_set_url)

        onto_server_value_set_url = f"{self.terminology_server_address}ValueSet/$expand?url={value_set_url}"
        response = self.session.get(onto_server_value_set_url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error("Request failed with status code %s:", response.status_code)
            logger.error(response.json()['issue'][0]['diagnostics'])
        return False

    @staticmethod
    def convert_lang_code_to_deepl(lang_code):
        if lang_code == "en":
            return "en-us"
        return lang_code

    def translate(self, value_set_url, source_lang, dry_run , batch_size=5):
        self.value_set = self.get_value_sets(value_set_url)
        if not self.value_set:
            return 0
        self.code_system_name = self.get_code_system_name()
        self.code_system_url = self.get_code_system_url().split("|")[0]
        self.code_system_version = self.get_code_system_url().split("|")[-1]
        self.code_system_template = json.load(open("CodeSystemTemplate.json", "r", encoding="utf-8"))

        concepts_to_translate = self.value_set["expansion"]["contains"]
        nr_of_values = len(concepts_to_translate)
        char_count = 0

        for value_index in range(0, nr_of_values, batch_size):
            concepts = []
            text = []

            for concept in concepts_to_translate[value_index:min(value_index + batch_size, nr_of_values)]:
                concepts.append(
                    {
                        "code": concept["code"],
                        "designation": []
                    }
                )
                text.append(concept["display"])
                char_count = char_count + len(concept["display"])

            for target_lang in self.target_langs:
                text_translated = text

                if target_lang != source_lang and not dry_run:
                    logger.info("Translating....")
                    translations = self.deepl_engine.translate_text(
                        text,
                        source_lang=source_lang,
                        target_lang=self.convert_lang_code_to_deepl(target_lang),
                        context=self.code_system_name
                    )

                    text_translated = [translation.text for translation in translations]

                for index in range(0, len(concepts)):
                    concepts[index]["designation"].append(
                        {
                            "value": text_translated[index],
                            "language": target_lang
                        }
                    )

            self.code_system_template["concept"].append(concepts)

        return char_count


    def save(self, target_folder):

        self.code_system_template["title"] = (
            f"{self.code_system_name} Supplement gebunden an CS-Version"
        )
        self.code_system_template["id"] = (
            f"fdpg-supplement-codesystem-{self.code_system_name}"
        )
        self.code_system_template["url"] = (
            f"https://fdpg.de/fhir/CodeSystem/{self.code_system_name}/translations"
        )
        self.code_system_template["supplements"] = (
            f"{self.code_system_url}|{self.code_system_version}"
        )
        self.code_system_template["count"] = len(self.code_system_template["concept"])
        self.code_system_template["name"] = f"{self.code_system_name}_supplement"

        if not os.path.exists(target_folder):
            os.makedirs(target_folder)

        with open(os.path.join(target_folder, f"{self.code_system_name}.json"), "w", encoding="utf-8") as file:
            json.dump(self.code_system_template, file, ensure_ascii=False)

        logger.info(
            "Translated %s. Saved at %s/%s.json",
            self.code_system_name,
            target_folder,
            self.code_system_name
        )
