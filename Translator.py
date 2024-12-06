import json
import os
from urllib.parse import urlparse
import logging
import deepl
from TerminologyDesignationResolver import TerminologyDesignationResolver

logger = logging.getLogger(__name__)


class Translator:
    def __init__(
            self, deepl_auth_key, session, terminology_server_address, target_langs, terminology_server_config
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
        self.code_systems = None
        self.max_bundle_size = 100
        self.terminologyResolver = TerminologyDesignationResolver(terminology_server_address, self.session, terminology_server_config)



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

    def get_value_sets(self, value_set_url) -> dict | bool:
        try:
            with open(value_set_url, "r", encoding="utf-8") as file:
                return json.load(file)
        except IOError:
            logger.info("%s not found among files locally, downloading instead ... ", value_set_url)

        onto_server_value_set_url = f"{self.terminology_server_address}ValueSet/$expand?url={value_set_url}"
        response = self.session.get(onto_server_value_set_url)
        if response.status_code == 200:
            logger.info("Downloaded Value-set")
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

    def translate(self, value_set_url, source_lang, dry_run , batch_size=5) -> int:
        """
        Translates a value_set with sources in the following order with the terminology_resolver:
            1. translations from the fdpg_plus_supplement_registry
            2. overriden by the existing official codesystem translations
            3. gaps are filled in by ai(deepl) in batches

        :param value_set_url:
        :param source_lang:
        :param dry_run: indicates if it is a test run for calculating expected word count/cost, If true nothing is sent to ai for translating
        :param batch_size: count of codes that are sent to ai at the same time
        :return: char_count
        """

        logger.info("")
        logger.info("Started Translating:" + value_set_url )

        self.value_set = self.get_value_sets(value_set_url)
        if not self.value_set:
            return 0
        self.code_system_name = self.get_code_system_name()
        self.code_system_url = self.get_code_system_url().split("|")[0]
        self.code_system_version = self.get_code_system_url().split("|")[-1]
        self.code_system_template = json.load(open("CodeSystemTemplate.json", "r", encoding="utf-8"))

        if "contains" not in self.value_set["expansion"]:
            return 0

        concepts_to_translate = self.value_set["expansion"]["contains"]
        self.terminologyResolver.load_base_designations_for_value_set(self.value_set)
        translated_concepts = {}

        for concept in concepts_to_translate:
            concept_code = concept.get('code')
            concept_system =self.terminologyResolver.code_systems.get(concept["system"])
            if  concept_system and concept_system.get('concept') and concept_system.get('concept').get(concept_code):
                template = {"de":"","en":"","display":concept.get('display')}
                translation = concept_system.get('concept').get(concept_code)
                if translation.get('de'):
                    template['de'] = translation.get('de')
                if translation.get('en'):
                    template['en'] = translation.get('en')
                translated_concepts[concept_code] = template
            else:
                translated_concepts[concept_code] = {"de":"","en":"","display":concept.get('display')}
                translated_concepts[concept_code][source_lang] = concept.get('display')

        batch_for_ai = {}
        char_count = 0
        for language in self.target_langs:
            i = 0
            for concept_code, concept_content in translated_concepts.items():
                i += 1
                if not concept_content.get(language) or concept_content.get(language) == "":
                    batch_for_ai[concept_code] = concept_content
                if batch_size <= len(batch_for_ai) or (i == len(translated_concepts) and len(batch_for_ai) > 0):
                    text = []
                    for code,content in batch_for_ai.items():
                        text.append(content.get('display'))
                        char_count = char_count + len(content.get('display'))

                    if not dry_run:
                        logger.info("Translating...." + value_set_url)
                        translations = self.deepl_engine.translate_text(
                            text,
                            source_lang=source_lang,
                            target_lang=self.convert_lang_code_to_deepl(language),
                        )

                        for (code,content),translation in zip(batch_for_ai.items(),translations):
                            content[language] = translation.text

                    batch_for_ai = {}

        for code,concept in translated_concepts.items():
            self.code_system_template["concept"].append({
            "code": code,
            "designation": [
                {
                    "language": "de",
                    "value": concept.get('de')
                },
                {
                    "language": "en",
                    "value": concept.get('en')
                }
            ]
        })

        logger.info("Finished Translating:" + value_set_url )
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
            json.dump(self.code_system_template, file, ensure_ascii=False, indent=4)

        logger.info(
            "Translated %s. Saved at %s/%s.json",
            self.code_system_name,
            target_folder,
            self.code_system_name
        )
