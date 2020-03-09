import logging
import json
import os
import uuid

from polyswarmartifact.schema.assertion import Assertion as AssertionMetadata
from polyswarmd.app import cache
from polyswarmd.utils import sha3, assertion_to_dict, cache_contract_view

logger = logging.getLogger(__name__)


def int_to_bytes(i):
    h = hex(i)[2:]
    return bytes.fromhex('0' * (64 - len(h)) + h)


def int_from_bytes(b):
    return int.from_bytes(b, byteorder='big')


def calculate_commitment(account, verdicts):
    nonce = os.urandom(32)
    account = int(account, 16)
    commitment = sha3(int_to_bytes(verdicts ^ int_from_bytes(sha3(nonce)) ^ account))
    return int_from_bytes(nonce), int_from_bytes(commitment)


# noinspection PyBroadException
@cache.memoize(30)
def substitute_metadata(
    uri, artifact_client, session, validate=AssertionMetadata.validate, redis=None
):
    """
    Download metadata from artifact service and validate it against the schema.

    :param uri: Potential artifact service uri string (or metadata string)
    :param artifact_client: Artifact Client for accessing artifacts stored on a service
    :param session: Requests session for ipfs request
    :param validate: Function that takes a loaded json blob and returns true if it matches the schema
    :param redis: Redis connection object
    :return: Metadata from artifact service, or original metadata
    """
    try:
        if artifact_client.check_uri(uri):
            content = json.loads(
                artifact_client.get_artifact(uri, session=session, redis=redis).decode('utf-8')
            )
        else:
            content = json.loads(uri)

        if validate(content):
            return content

    except json.JSONDecodeError:
        # Expected when people provide incorrect metadata. Not stack worthy
        logger.warning('Metadata retrieved from IPFS does not match schema')
    except Exception:
        logger.exception(f'Error getting metadata from {artifact_client.name}')

    return uri
