import copy
from enum import Enum

from typing import List, TypeVar


class BundleType(Enum):
    DOCUMENT = "document"
    MESSAGE = "message"
    TRANSACTION = "transaction"
    TRANSACTION_RESPONSE = "transaction-response"
    BATCH = "batch"
    BATCH_RESPONSE = "batch-response"
    HISTORY = "history"
    SEARCHSET = "searchset"
    COLLECTION = "collection"


def create_bundle(bundle_type: BundleType):
    return {
        "resourceType": "Bundle",
        "type": bundle_type.value,
        "entry": []
    }


def extract_designation(parameters: dict, language: str) -> str | None:
    """
    Helper function for extracting language code specific designation display value from `Parameters` resource
    :param parameters: `Parameters` resource to extract display value from
    :param language: Language code identifying display value to extract
    :return: Either `str` display value or `None` if no designation for language codes exists
    """
    for designation in filter(lambda p: p.get("name") == "designation", parameters.get("parameter", [])):
        part = designation.get("part")
        if part:
            designation_language = list(filter(lambda p: p.get("name") == "language", part))[0].get("valueCode")
            designation_use = list(filter(lambda p: p.get("name") == "use", part))[0].get("valueCoding").get("code")
            if designation_language == language and designation_use == "display":
                return list(filter(lambda p: p.get("name") == "value", part))[0].get("valueString")
    return None

T = TypeVar("T")

def chunks(coll: List[T], chunk_size: int = 10) -> List[List[T]]:
    for i in range(0, len(coll), chunk_size):
        yield coll[i:i + chunk_size]


def split_bundle(bundle: dict, chunk_size: int = 10) -> List[dict]:
    if not bundle.get("entry", []):
        return [bundle]
    else:
        bundles = []
        for chunk in chunks(bundle.get("entry"), chunk_size):
            # Perform shallow copy as the `entry` element will be replaced with its chunk
            bundle_chunk = copy.copy(bundle)
            bundle_chunk["entry"] = chunk
            bundles.append(bundle_chunk)
        return bundles
