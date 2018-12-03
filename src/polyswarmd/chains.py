import functools
import logging

from flask import current_app as app, g, request

from polyswarmd.response import failure

logger = logging.getLogger(__name__)

def chain(_func=None, chain_name=None, account_required=True):
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
            g.eth_address = request.args.get('account')
            if not g.eth_address and account_required:
                return failure('Account must be provided', 400)

            c = chain_name
            if c is None:
                c = request.args.get('chain', 'side')

            logger.info("Chain: %s", c)

            chain = app.config['POLYSWARMD'].chains.get(c)
            if not chain:
                chain_options = ", ".join(app.config['POLYSWARMD'].chains)
                return failure('Chain must one of {0}'.format(', '.join(chain_options)), 400)

            g.chain = chain
            return func(*args, **kwargs)

        return wrapper

    if _func is None:
        return decorator_wrapper

    return decorator_wrapper(_func)
