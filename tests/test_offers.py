from .utils import failed, heck


# def test_get_balance_total_stake(client, mock_w3, token_address, balances):
#     assert sane(
#         response=client.get(f'/offers/'),
#         expected=heck({
#             'result': str(balances[token_address]),
#             'status': 'OK'
#         })
#     )

#     assert failed(client.get(f'/balances/INVALID/staking/total'))
