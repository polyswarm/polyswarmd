import uuid


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
        'commitment': str(assertion[3]),
        'nonce': str(assertion[4]),
        'verdicts': int_to_bool_list(assertion[5]),
        'metadata': assertion[6],
    }


def new_assertion_event_to_dict(new_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=new_assertion_event.bountyGuid)),
        'author': new_assertion_event.author,
        'index': new_assertion_event.index,
        'bid': str(new_assertion_event.bid),
        'mask': int_to_bool_list(new_assertion_event.mask),
        'commitment': str(new_assertion_event.commitment),
    }


def revealed_assertion_event_to_dict(revealed_assertion_event):
    return {
        'bounty_guid': str(uuid.UUID(int=revealed_assertion_event.bountyGuid)),
        'author': revealed_assertion_event.author,
        'index': revealed_assertion_event.index,
        'nonce': str(revealed_assertion_event.bid),
        'verdicts': int_to_bool_list(revealed_assertion_event.verdicts),
        'metadata': revealed_assertion_event.metadata,
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
