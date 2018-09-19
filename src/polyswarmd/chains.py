import functools
import os

from flask import g, request

from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

from polyswarmd.response import failure
from polyswarmd.config import config_location, chain_id as id_chains, eth_uri as eth_chains, nectar_token_address as nectar_chains, bounty_registry_address as bounty_chains, offer_registry_address, free as free_chains, erc20_relay_address as erc20_relay_chains
from polyswarmd.eth import bind_contract

web3_chains = {}
# Create token bindings for each chain
bounty_registry_chains = {}
nectar_token_chains = {}
arbiter_staking_chains = {}

# exists only on home
offer_registry_home = None
offer_lib_home = None

for chain in ('home', 'side'):
    # Grab all the values for the chain. If they aren't defined, skip
    eth_uri = eth_chains.get(chain)
    bounty_registry_address = bounty_chains.get(chain)
    nectar_token_address = nectar_chains.get(chain)

    if (
            eth_uri is not None
            and bounty_registry_address is not None
            and nectar_token_address is not None
        ):

        web3 = Web3(HTTPProvider(eth_uri))
        web3.middleware_stack.inject(geth_poa_middleware, layer=0)
        web3_chains[chain] = web3
        nectar_token_chains[chain] = bind_contract(
            web3, nectar_token_address,
            os.path.join(config_location, 'contracts', 'NectarToken.json'))

        bounty_registry_chains[chain] = bind_contract(
            web3, bounty_registry_address,
            os.path.join(config_location, 'contracts', 'BountyRegistry.json'))
        arbiter_staking_chains[chain] = bind_contract(
            web3, bounty_registry_chains[chain].functions.staking().call(),
            os.path.join(config_location, 'contracts', 'ArbiterStaking.json'))

        if chain == 'home':
            offer_registry_home = bind_contract(
                web3, offer_registry_address[chain],
                os.path.join(config_location, 'contracts', 'OfferRegistry.json'))

            offer_lib_address = offer_registry_home.functions.offerLib().call()

            offer_lib_home = bind_contract(
                web3, offer_lib_address,
                os.path.join(config_location, 'contracts', 'OfferLib.json'))

def select_chain(_func=None, *, chain_name=None):
    """This decorator takes the chain passed as a request arg and modifies a set of globals.
       There are a few guarantees made by this function.

       If any of the values for the given chain are missing, the decorator will skip the function and return an error to the user. (500)
       If the chain is not recognized, it will return an error to the user. (400)
       If it is the home chain, the offer contract address and  bindings will also be validated, or an error returned. (500)
    """
    @functools.wraps(_func)
    def decorator_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal chain_name
            if chain_name is None:
                chain_name = request.args.get('chain', 'home')

            if chain_name != "home" and chain_name != "side":
                return failure('Chain must be either home or side', 400)

            if chain_name == "side" and chain_name not in nectar_chains.keys():
                return failure('Side chain not supported in this instance of polyswarmd', 400)

            chain_data = {
                "chain_id": id_chains.get(chain_name),
                "nectar_token_address": nectar_chains.get(chain_name),
                "bounty_registry_address": bounty_chains.get(chain_name),
                "erc20_relay_address": erc20_relay_chains.get(chain_name),
                "eth_uri": eth_chains.get(chain_name),
                "free": free_chains.get(chain_name),
                "bounty_registry": bounty_registry_chains.get(chain_name),
                "nectar_token": nectar_token_chains.get(chain_name),
                "arbiter_staking": arbiter_staking_chains.get(chain_name),
                "web3": web3_chains.get(chain_name),
            }
            if chain_name == "home":
                chain_data["offer_lib"] = offer_lib_home
                chain_data["offer_registry"] = offer_registry_home


            if validate(chain_data):
                # Add all validated fields to g
                for k, v in chain_data.items():
                    g.setdefault(k, default=v)

                # Add these if not defined (which means we are not on the home chain, because that is already validated)
                if not g.get('offer_lib'):
                    g.offer_lib = None

                if not g.get('offer_registry'):
                    g.offer_registry = None

                return func(*args, **kwargs)
            else:
                return failure("Server experienced an error finding %s chain values" % chain_name, 500)
        return wrapper

    if _func is None:
        return decorator_wrapper
    else:
        return decorator_wrapper(_func)


def validate(chain_data):
    for v in chain_data:
        if v is None:
            return False

    return True
