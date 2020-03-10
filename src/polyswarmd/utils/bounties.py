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


@cache.memoize(1)
def get_txpool():
    from flask import g
    return g.chain.w3.txpool.inspect


@cache.memoize(1)
def bounty_fee(bounty_registry):
    return bounty_registry.functions.bountyFee().call()


@cache.memoize(1)
def assertion_fee(bounty_registry):
    return bounty_registry.functions.assertionFee().call()


@cache.memoize(1)
def bounty_amount_min(bounty_registry):
    return bounty_registry.functions.BOUNTY_AMOUNT_MINIMUM().call()


@cache.memoize(1)
def assertion_bid_min(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MINIMUM().call()


@cache.memoize(1)
def assertion_bid_max(bounty_registry):
    return bounty_registry.functions.ASSERTION_BID_ARTIFACT_MAXIMUM().call()


@cache.memoize(1)
def staking_total_max(arbiter_staking):
    return arbiter_staking.functions.MAXIMUM_STAKE().call()


@cache.memoize(1)
def staking_total_min(arbiter_staking):
    return arbiter_staking.functions.MINIMUM_STAKE().call()
