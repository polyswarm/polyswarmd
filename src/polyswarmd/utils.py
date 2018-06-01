import uuid
from polyswarmd.eth import offer_lib, web3 as web3_chains


def bool_list_to_int(bs):
    return sum([1 << n if b else 0 for n, b in enumerate(bs)])


def int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]


def uint256_list_to_hex_string(us):
    return hex(sum([x << (256 * n) for n, x in enumerate(us)]))


def bounty_to_dict(bounty):
    return {
        'guid': str(uuid.UUID(int=bounty[0])),
        'author': bounty[1],
        'amount': str(bounty[2]),
        'uri': bounty[3],
        'num_artifacts': bounty[4],
        'expiration': bounty[5],
        'resolved': bounty[6],
        'bloom': uint256_list_to_hex_string(bounty[7]),
        'voters': bounty[8],
        'verdicts': int_to_bool_list(bounty[9]),
        'bloom_votes': bounty[10],
    }


def new_bounty_event_to_dict(new_bounty_event):
    return {
        'guid': str(uuid.UUID(int=new_bounty_event.guid)),
        'author': new_bounty_event.author,
        'amount': str(new_bounty_event.amount),
        'uri': new_bounty_event.artifactURI,
        'expiration': str(new_bounty_event.expirationBlock),
    }


def assertion_to_dict(assertion):
    return {
        'author': assertion[0],
        'bid': str(assertion[1]),
        'mask': int_to_bool_list(assertion[2]),
        'verdicts': int_to_bool_list(assertion[3]),
        'metadata': assertion[4],
    }


def new_assertion_event_to_dict(new_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_assertion_event.bountyGuid)),
        'author': new_assertion_event.author,
        'index': new_assertion_event.index,
        'bid': str(new_assertion_event.bid),
        'mask': int_to_bool_list(new_assertion_event.mask),
        'verdicts': int_to_bool_list(new_assertion_event.verdicts),
        'metadata': new_assertion_event.metadata,
    }


def new_verdict_event_to_dict(new_verdict_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_verdict_event.bountyGuid)),
        'verdicts': int_to_bool_list(new_verdict_event.verdicts),
    }

def new_transfer_event_to_dict(new_transfer_event):
    return {
        'from': new_transfer_event['from'],
        'to': new_transfer_event['to'],
        'value': str(new_transfer_event['value'])
    }

def channel_to_dict(channel_data):
    return {
        'msig_address': channel_data[0],
        'ambassador': channel_data[1],
        'expert': channel_data[2]
    }

def state_to_dict(state):
    # gets state of non required state
    offer_info = offer_lib.function.getOfferState(state)
    web3 = web3_chains['home']

    return {
        'isClosed': web3.toInt(offer_lib.functions.getCloseFlag(state)),
        'nonce': web3.toInt(offer_lib.functions.getSequence(state)),
        'ambassador': offer_lib.functions.getPartyA(state),
        'expert': offer_lib.functions.getPartyB(state),
        'msig_address': offer_lib.functions.getMultiSigAddress(state),
        'ambassador_balance': web3.toInt(offer_lib.functions.getBalanceA(state)),
        'expert_balance': web3.toInt(offer_lib.functions.getBalanceB(state)),
        'token': offer_lib.functions.getTokenAddress(state),
        'offer_amount': web3.toInt(offer_lib.functions.getCloseFlag(state)),
        'ipfs_uri': web3.toText(offer_info[3]),
        'verdicts': offer_info[5]
    }
