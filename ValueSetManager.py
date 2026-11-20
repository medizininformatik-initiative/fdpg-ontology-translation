import json
import logging
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Final, Optional, overload

import requests
from dotenv import load_dotenv
from fhir.resources.R4B.valueset import ValueSet
from pydantic import ValidationError

from models import CachedValueSet
from TerminologyClient import TerminologyClient

logger = logging.getLogger(__name__)


_UNVERSIONED: Final = ""


class ValueSetIndex:
    def __init__(self) -> None:
        """
        This class structures valueSets by:
        - url
            - version
        So there can be multiple valueSets with the same url but with different versions

        Because not all valueSets even present a version attribute, they are stored under _UNVERSIONED.
        There is only room for one _UNVERSIONED valueSet per valueSet url
        """
        self._index: dict[str, dict[str, ValueSet]] = {}

    @staticmethod
    def _key(version: str | None) -> str:
        return version or _UNVERSIONED

    def add(self, value_set: ValueSet) -> None:
        if value_set.url is None:
            raise ValueError("ValueSet has no url")

        versions = self._index.get(value_set.url)
        if versions is None:
            versions = {}
            self._index[value_set.url] = versions
        versions[self._key(value_set.version)] = value_set

    @overload
    def remove(self, value_set: ValueSet, /) -> ValueSet | None: ...
    @overload
    def remove(self, url: str, version: None = None, /) -> list[ValueSet]: ...
    @overload
    def remove(self, url: str, version: str, /) -> ValueSet | None: ...

    def remove(
        self, target: ValueSet | str, version: str | None = None, /
    ) -> ValueSet | list[ValueSet] | None:
        if isinstance(target, ValueSet):
            if version is not None:
                raise TypeError(
                    "pass either a ValueSet or url or (url and version), not both"
                )
            if target.url is None:
                raise ValueError("ValueSet has no url")
            return self.remove(target.url, self._key(target.version))

        if version is None:  # remove all versions of this url
            return list(self._index.pop(target, {}).values())

        versions = self._index.get(target)
        if versions is None:
            return None
        removed = versions.pop(version, None)
        if not versions:
            del self._index[target]
        return removed

    @overload
    def find(self, url: str, version: None = None, /) -> list[ValueSet]: ...
    @overload
    def find(self, url: str, version: str, /) -> ValueSet | None: ...

    def find(
        self, url: str, version: str | None = None, /
    ) -> list[ValueSet] | ValueSet | None:
        versions = self._index.get(url, {})
        if version is None:
            return list(versions.values())
        return versions.get(version)

    def items(self) -> Iterator[tuple[tuple[str, str], ValueSet]]:
        for url, versions in self._index.items():
            for version, value_set in versions.items():
                yield (url, version), value_set

    def values(self) -> Iterator[ValueSet]:
        for versions in self._index.values():
            yield from versions.values()


class ValueSetManager:
    local_index: ValueSetIndex

    def __init__(
        self,
        ingest_folder: Path | None = None,
        package_cache_folder: Path | None = None,
        terminology_client: TerminologyClient | None = None,
        cache_folder: Path = Path("value-set-cache"),
    ):
        """
        Class that holds an index of all expanded ValueSets to be translated
        :param ingest_folder: Input folder of the script
        :param package_cache_folder: Output taken from the package manager from the fhir-ontology-generator
        """
        self.package_cache_folder: Path | None = package_cache_folder
        self.ingest_folder: Path | None = ingest_folder
        self.local_index = ValueSetIndex()
        self.terminology_client: TerminologyClient | None = terminology_client
        self.cache_folder: Path = cache_folder
        self.ingest()

    def ingest(self):
        """
        Builds the index from the ValueSets in the package cache + input folder.
        Each ValueSet (url + version) is taken from the cache if it was expanded before,
        otherwise it is expanded on the server and cached. Failed expansions are not cached,
        so they are retried on the next run.
        """
        self.cache_folder.mkdir(exist_ok=True)

        if self.package_cache_folder is not None:
            self.process_package_cache()

        if self.ingest_folder is not None:
            self.process_input_folder()

    def _cache_file(self, url: str, version: str | None) -> Path:
        # one file per url + version, e.g. www.medizininformatik-initiative.de_fhir_..._Vitalstatus_2026.0.0.json
        key = f"{url.split('://')[-1]}_{version or 'unversioned'}"
        return self.cache_folder / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', key)}.json"

    def _add_expanded(self, value_set: ValueSet) -> None:
        cache_file = self._cache_file(value_set.url, value_set.version)

        if cache_file.exists():
            # the cache was validated when it was expanded; the slim model skips the slow FHIR validation
            self.local_index.add(
                CachedValueSet.model_validate_json(
                    cache_file.read_text(encoding="utf-8")
                )
            )
            return

        if self.terminology_client is None:
            logger.error(
                f"Could not expand valueset {value_set.url}|{value_set.version}: not cached and no terminology server connection"
            )
            return

        expanded = self.terminology_client.expand_value_set(
            url=value_set.url, version=value_set.version
        )
        if expanded is None:
            return  # not cached => retried on the next run

        cache_file.write_text(expanded.model_dump_json(indent=2), encoding="utf-8")
        self.local_index.add(expanded)

    def process_package_cache(self):
        """
        Populate the index with ValueSets from the package cache.
        """
        if self.package_cache_folder is None:
            logger.warning(
                "No FHIR package cache folder was provided. Nothing to process"
            )
            return

        logger.info("Processing package folder")

        for package in self.package_cache_folder.iterdir():
            logger.info(package.name)
            if package.is_file():
                continue
            for file in (package / "package").iterdir():
                if not file.is_file() or file.suffix != ".json":
                    continue
                self.load_value_set_from_file(file)

            # TODO: Extract all valueSets from all bindings and include them in the index

    def process_input_folder(self):
        """
        Expand and populate the local index with valueSets from the ingest folder
        """
        if self.ingest_folder is None:
            logger.warning(
                "No unexpanded valueSet input folder was provided. Nothing to process"
            )
            return
        logger.info("Processing input folder")
        for file in self.ingest_folder.iterdir():
            self.load_value_set_from_file(file)

    def load_value_set_from_file(self, file: Path):
        if not file.is_file() or file.suffix != ".json":
            logger.error(f"Failed to load {file} : file is not a json file")
            return

        text = file.read_text(encoding="utf-8")
        # cheap type check first; the slow FHIR validation only runs for actual ValueSets
        if json.loads(text).get("resourceType") != "ValueSet":
            return

        try:
            valueSet: ValueSet = ValueSet.model_validate_json(text)
        except ValidationError as err:
            # not a ValueSet => ignore
            logger.debug("Not a ValueSet")
            return

        self._add_expanded(valueSet)


if __name__ == "__main__":
    load_dotenv()
    session = requests.Session()
    session.cert = (os.getenv("SERVER_CERTIFICATE"), os.getenv("PRIVATE_KEY"))

    vsm = ValueSetManager(
        package_cache_folder=Path("fhir-package-cache"),
        # ingest_folder=Path("value-sets"),
        terminology_client=TerminologyClient(session, os.getenv("TERMINOLOGY_SERVER")),
    )
    vsm.ingest()
    vsm.export_to_translation_config(target_folder=Path("expanded-value-sets"))

# go after binding -> expand -> build triplets -> translate missing combinations
