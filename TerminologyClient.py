import json
import logging
from pathlib import Path
from typing import List

from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.codesystem import CodeSystem
from fhir.resources.R4B.valueset import ValueSet
from pydantic import ValidationError
from requests import Session

logger = logging.getLogger(__name__)


EXPAND_PAGE_SIZE = 100_000  # Paging for large requests


class NotFoundError(Exception):
    pass


class TerminologyClient:
    def __init__(
        self, session: Session, terminology_server_address, backup_server_address=None
    ):
        self.session: Session = session
        self.terminology_server_address: str = terminology_server_address
        # every request goes to the main server first, the backup is only asked if nothing was found
        self.servers: list[str] = [
            s for s in (terminology_server_address, backup_server_address) if s
        ]
        self.report_file: Path = Path("terminology-server-report.json")
        # init report file
        self.report_file.write_text("{}", encoding="utf-8")

    def _with_fallback(self, request, *args, **kwargs):
        """Run request(server, ...) on the main server, then on the backup if the result is empty."""
        result = None
        for server in self.servers:
            result = request(server, *args, **kwargs)
            if result:
                return result
            logger.info(f"Nothing found on {server} for {args or kwargs}")
        return result

    def __report_missing_value_set(self, url: str, version: str):
        # log to file which valuesets are missing for easier communication with the server team
        report_file = json.loads(self.report_file.read_text(encoding="utf-8"))
        if report_file.get("Missing ValueSets", None) is None:
            report_file["Missing ValueSets"] = []

        report_file["Missing ValueSets"].append({"url": url, "version": version})
        self.report_file.write_text(json.dumps(report_file), encoding="utf-8")

    def expand_value_set(self, url: str, version: str | None = None) -> ValueSet | None:
        expanded = self._with_fallback(self._expand_value_set, url, version)
        if expanded is None:
            logger.error(f"Could not expand ValueSet {url}|{version} on any server")
            self.__report_missing_value_set(url, version)
        return expanded

    def _expand_value_set(
        self, server: str, url: str, version: str | None = None
    ) -> ValueSet | None:
        expanded_value_set_json = None
        offset = 0
        while True:
            page = self.session.get(
                f"{server}ValueSet/$expand",
                # the $expand parameter is "valueSetVersion"; "version" would be ignored (=> latest version)
                params={
                    "url": url,
                    "valueSetVersion": version,
                    "includeDesignations": "true",
                    "offset": offset,
                    "count": EXPAND_PAGE_SIZE,
                },
            ).json()

            if page.get("resourceType") == "OperationOutcome":
                logger.info(
                    f"{server} could not expand ValueSet {url}|{version}: {page}"
                )
                return None

            contains = page.get("expansion", {}).get("contains", [])
            if expanded_value_set_json is None:
                expanded_value_set_json = page  # first page carries the ValueSet itself
            else:
                expanded_value_set_json["expansion"]["contains"] += contains

            offset += len(contains)
            total = page.get("expansion", {}).get("total")
            if not contains or total is None or offset >= total:
                break

        # the merged expansion is complete, not a single page
        expanded_value_set_json.get("expansion", {}).pop("offset", None)

        expanded_value_set: ValueSet
        try:
            expanded_value_set = ValueSet.model_validate(expanded_value_set_json)
            return expanded_value_set
        except ValidationError as err:
            logger.error(f"Could not expand valueSet because: \n {err}")
            return None

    def get_code_system(
        self, url: str | None = None, version: str | None = None, id: str | None = None
    ) -> list[CodeSystem]:
        """Read one CodeSystem by server id, or search by url (+ version). Empty list on if no cs found or failure."""
        return self._with_fallback(
            self._get_code_system, url=url, version=version, id=id
        )

    def _get_code_system(
        self,
        server: str,
        url: str | None = None,
        version: str | None = None,
        id: str | None = None,
    ) -> list[CodeSystem]:
        if id is not None:
            resp = self.session.get(f"{server}CodeSystem/{id}")
            return [CodeSystem.model_validate_json(resp.text)] if resp.ok else []

        next_url = f"{server}CodeSystem"
        params = {
            "url": url,
            "version": version,
            "_count": 100,
        }  # requests drops None values
        result: list[CodeSystem] = []
        while next_url:
            resp = self.session.get(next_url, params=params)
            if not resp.ok:
                logger.error(
                    f"Could not get CodeSystem {url}|{version}: {resp.status_code} {resp.text}"
                )
                break
            bundle = resp.json()
            result += [
                CodeSystem.model_validate(e["resource"])
                for e in bundle.get("entry") or []
            ]
            next_url = next(
                (l["url"] for l in bundle.get("link", []) if l["relation"] == "next"),
                None,
            )
            params = None  # the 'next' link already contains the search parameters
        return result

    def fetch_existing_supplements(self) -> Bundle | None:
        return self._with_fallback(self._fetch_existing_supplements)

    def _fetch_existing_supplements(self, server: str) -> Bundle | None:
        resp = self.session.get(
            f"{server}CodeSystem?content-mode=supplement&_elements=url,version,status,content,supplements"
        )

        if resp.status_code != 200:
            logger.error(f"Could not get supplements: {resp.status_code}")
            return

        resp_json = resp.json()

        if resp_json.get("resourceType") == "OperationOutcome":
            logger.error(f"Could not get supplements because: {resp_json}")
            return None

        bundle = Bundle.model_validate_json(resp.text)
        return (
            bundle if bundle.entry else None
        )  # empty search result => ask the backup server
