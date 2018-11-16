import logging
import re
import uuid
from flask import g
from polyswarmd.eth import zero_address

logger = logging.getLogger(__name__)


def bool_list_to_int(bs):
    return sum([1 << n if b else 0 for n, b in enumerate(bs)])


def int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]


def safe_int_to_bool_list(num, max):
    if int(num) == 0:
        return [False] * int(max)
    else:
        return int_to_bool_list(num)


def uint256_list_to_hex_string(us):
    return hex(sum([x << (256 * n) for n, x in enumerate(us)]))


def bounty_to_dict(bounty):
    bounty_has_voters_and_verdicts = len(bounty) > 10

    retval = {
        'guid': str(uuid.UUID(int=bounty[0])),
        'author': bounty[1],
        'amount': str(bounty[2]),
        'uri': bounty[3],
        'num_artifacts': bounty[4],
        'expiration': bounty[5],
        'assigned_arbiter': bounty[6],
        'quorum_reached': bounty[7],
        'quorum_reached_block': bounty[8],
        'quorum_mask': safe_int_to_bool_list(bounty[9], bounty[4]),
    }
    if bounty_has_voters_and_verdicts:
        retval['bloom'] = uint256_list_to_hex_string(bounty[10])
        retval['bloom_votes'] = bounty[13]
    return retval


def new_bounty_event_to_dict(new_bounty_event):
    return {
        'guid': str(uuid.UUID(int=new_bounty_event.guid)),
        'author': new_bounty_event.author,
        'amount': str(new_bounty_event.amount),
        'uri': new_bounty_event.artifactURI,
        'expiration': str(new_bounty_event.expirationBlock),
    }


def assertion_to_dict(assertion, num_artifacts):
    return {
        'author': assertion[0],
        'bid': str(assertion[1]),
        'mask': safe_int_to_bool_list(assertion[2], num_artifacts),
        'commitment': str(assertion[3]),
        'nonce': str(assertion[4]),
        'verdicts': safe_int_to_bool_list(assertion[5], num_artifacts),
        'metadata': assertion[6],
    }


def new_assertion_event_to_dict(new_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_assertion_event.bountyGuid)),
        'author': new_assertion_event.author,
        'index': new_assertion_event.index,
        'bid': str(new_assertion_event.bid),
        'mask': safe_int_to_bool_list(new_assertion_event.mask, new_assertion_event.numArtifacts),
        'commitment': str(new_assertion_event.commitment),
    }


def revealed_assertion_event_to_dict(revealed_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=revealed_assertion_event.bountyGuid)),
        'author': revealed_assertion_event.author,
        'index': revealed_assertion_event.index,
        'nonce': str(revealed_assertion_event.nonce),
        'verdicts': safe_int_to_bool_list(revealed_assertion_event.verdicts, revealed_assertion_event.numArtifacts),
        'metadata': revealed_assertion_event.metadata,
    }

def verdict_to_dict(vote, num_artifacts):
    return {
        'arbiter': vote[0],
        'verdicts': safe_int_to_bool_list(vote[1], num_artifacts),
        'valid_bloom': vote[2],
    }

def new_verdict_event_to_dict(new_verdict_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_verdict_event.bountyGuid)),
        'verdicts': safe_int_to_bool_list(new_verdict_event.verdicts, new_verdict_event.numArtifacts),
        'voter': new_verdict_event.voter,
    }


def settled_bounty_event_to_dict(new_settled_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_settled_event.bountyGuid)),
        'settled_block': new_settled_event.block,
        'settler': new_settled_event.settler,
    }


def new_quorum_event_to_dict(new_quorum_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_quorum_event.bountyGuid)),
        'quorum_block': new_quorum_event.block,
    }


def transfer_event_to_dict(transfer_event):
    return {
        'from': transfer_event['from'],
        'to': transfer_event['to'],
        'value': str(transfer_event['value']),
    }


def new_deposit_event_to_dict(deposit_event):
    return {
        'from': deposit_event['from'],
        'value': deposit_event['value'],
    }


def new_withdrawal_event_to_dict(withdrawal_event):
    return {
        'to': withdrawal_event['to'],
        'value': withdrawal_event['value'],
    }


def channel_to_dict(channel_data):
    return {
        'msig_address': channel_data[0],
        'ambassador': channel_data[1],
        'expert': channel_data[2],
    }


def state_to_dict(state):
    if not g.chain:
        raise ValueError('g.chain not found')

    # gets state of non required state
    offer_info = g.chain.offer_lib.contract.functions.getOfferState(state).call()

    return {
        'isClosed': g.chain.offer_lib.contract.functions.getCloseFlag(state).call(),
        'nonce': g.chain.offer_lib.contract.functions.getSequence(state).call(),
        'ambassador': g.chain.offer_lib.contract.functions.getPartyA(state).call(),
        'expert': g.chain.offer_lib.contract.functions.getPartyB(state).call(),
        'msig_address': g.chain.offer_lib.contract.functions.getMultiSigAddress(state).call(),
        'ambassador_balance': g.chain.offer_lib.contract.functions.getBalanceA(state).call(),
        'expert_balance': g.chain.offer_lib.contract.functions.getBalanceB(state).call(),
        'token': g.chain.offer_lib.contract.functions.getTokenAddress(state).call(),
        'offer_amount': g.chain.w3.toInt(offer_info[1]),
        'mask': int_to_bool_list(g.chain.w3.toInt(offer_info[6])),
        'verdicts': int_to_bool_list(g.chain.w3.toInt(offer_info[7])),
    }


def new_init_channel_event_to_dict(new_init_event):
    return {
        'guid': str(uuid.UUID(int=new_init_event.guid)),
        'ambassador': new_init_event.ambassador,
        'expert': new_init_event.expert,
        'multi_signature': new_init_event.msig,
    }


def new_settle_challenged_event(new_event):
    return {
        'challenger': new_event.challenger,
        'nonce': new_event.sequence,
        'settle_period_end': new_event.settlementPeriodEnd,
    }


def new_settle_started_event(new_event):
    return {
        'initiator': new_event.initiator,
        'nonce': new_event.sequence,
        'settle_period_end': new_event.settlementPeriodEnd,
    }


def new_cancel_agreement_event_to_dict(new_event):
    return {
        'expert': new_event._expert,
        'ambassador': new_event._ambassador,
    }


# https://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
def camel_case_to_snake_case(s):
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', s)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def to_padded_hex(val):
    if not g.chain:
        raise ValueError('g.chain not found')

    if type(val) == str:
        if val.startswith('0x'):
            padded_hex = g.chain.w3.toHex(hexstr=val)[2:]
        else:
            padded_hex = g.chain.w3.toHex(text=val)[2:]
    else:
        padded_hex = g.chain.w3.toHex(val)[2:]

    l = 64 - len(padded_hex)

    for i in range(0, l):
        padded_hex = '0' + padded_hex

    return padded_hex


def dict_to_state(state_dict):
    state_str = '0x'

    state_str = state_str + to_padded_hex(state_dict['close_flag'])
    state_str = state_str + to_padded_hex(state_dict['nonce'])
    state_str = state_str + to_padded_hex(state_dict['ambassador'])
    state_str = state_str + to_padded_hex(state_dict['expert'])
    state_str = state_str + to_padded_hex(state_dict['msig_address'])
    state_str = state_str + to_padded_hex(state_dict['ambassador_balance'])
    state_str = state_str + to_padded_hex(state_dict['expert_balance'])
    state_str = state_str + to_padded_hex(state_dict['token_address'])
    state_str = state_str + to_padded_hex(int(state_dict['guid']))
    state_str = state_str + to_padded_hex(state_dict['offer_amount'])

    # no longer storing in contract state
    if 'artifact_hash' in state_dict:
        state_str = state_str + to_padded_hex('')

    if 'ipfs_hash' in state_dict:
        state_str = state_str + to_padded_hex(state_dict['ipfs_hash'])
    else:
        state_str = state_str + to_padded_hex('')

    if 'engagement_deadline' in state_dict:
        state_str = state_str + to_padded_hex(
            state_dict['engagement_deadline'])
    else:
        state_str = state_str + to_padded_hex('')

    if 'assertion_deadline' in state_dict:
        state_str = state_str + to_padded_hex(state_dict['assertion_deadline'])
    else:
        state_str = state_str + to_padded_hex('')

    if 'mask' in state_dict:
        state_str = state_str + to_padded_hex(state_dict['mask'])
    else:
        state_str = state_str + to_padded_hex('')

    if 'verdicts' in state_dict:
        state_str = state_str + to_padded_hex(state_dict['verdicts'])
    else:
        state_str = state_str + to_padded_hex('')

    if 'meta_data' in state_dict:
        state_str = state_str + to_padded_hex(state_dict['meta_data'])
    else:
        state_str = state_str + to_padded_hex('')

    return state_str


def validate_ws_url(uri):
    regex = re.compile(
        r'^(?:ws)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return re.match(regex, uri) is not None
