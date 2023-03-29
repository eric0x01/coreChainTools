import os
import sys
import pathlib
import time
import logging
import toml
from web3 import Web3
from web3.middleware import geth_poa_middleware, construct_sign_and_send_raw_middleware
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.constants import ADDRESS_ZERO
from eth_utils import remove_0x_prefix, add_0x_prefix
from eth_account import Account
from eth_account.account import LocalAccount
from dotenv import load_dotenv
from add_path import *
from src.constant import CoreContract
from src.log_config import config_logging
from src.utils import split_list_by_n, load_abi


def get_mint_address_list(w3: Web3, contract_address: str, from_block: int, end_block: int, step=10000) -> set:
    assert from_block < end_block
    address_list = []
    _start_block = from_block
    while _start_block < end_block:
        _end_block = min([_start_block + step, end_block])
        event_filter = w3.eth.filter({
            "address": contract_address,
            "topics": [
                w3.keccak(text="Transfer(address,address,uint256)").hex(),
                add_0x_prefix(remove_0x_prefix(ADDRESS_ZERO).rjust(64, '0')),
            ],
            "fromBlock": _start_block,
            "toBlock": _end_block
        })
        for event in event_filter.get_all_entries():
            to_address = add_0x_prefix(remove_0x_prefix(event['topics'][2].hex())[-40:])
            address_list.append(Web3.toChecksumAddress(to_address))
        _start_block = _end_block
    return set(address_list)


def get_send_reward_address_list(w3: Web3, contract_address: str, from_block: int, end_block: int, step=10000) -> set:
    assert from_block < end_block
    address_list = []
    _start_block = from_block
    while _start_block < end_block:
        _end_block = min([_start_block + step, end_block])
        event_filter = w3.eth.filter({
            "address": contract_address,
            "topics": [
                w3.keccak(text="sendValue(address,bool)").hex()
            ],
            "fromBlock": _start_block,
            "toBlock": _end_block
        })
        for event in event_filter.get_all_entries():
            receiver = add_0x_prefix(remove_0x_prefix(event['topics'][1].hex())[-40:])
            address_list.append(Web3.toChecksumAddress(receiver))
        _start_block = _end_block
    return set(address_list)


if __name__ == '__main__':
    def check_cross_chain_user():
        global current_check_num

        latest_block_num = w3.eth.block_number
        if latest_block_num - current_check_num < 100:
            return

        end_block_num = min([current_check_num + 10000, latest_block_num])
        cross_chain_users = set()
        for contract in (CoreContract.USDC, CoreContract.USDT, CoreContract.WETH):
            mint_address_list = get_mint_address_list(w3, contract, current_check_num, end_block_num)
            cross_chain_users.update(mint_address_list)

        valid_users = cross_chain_users.difference(reward_receiver_address_set)
        send_reward(list(valid_users))
        reward_receiver_address_set.update(cross_chain_users)
        current_check_num = end_block_num
        logging.info(f"reward address number: {len(reward_receiver_address_set)}")
        logging.info(f"current check block height: {current_check_num}")


    def send_reward(address_list: list):
        for address_collection in split_list_by_n(address_list, 100):
            if mock_send:
                logging.info(f"send to {address_collection}")
            else:
                tx_dict = batch_send_contract.functions.batchSend(
                    address_collection, Web3.toWei(0.1, 'ether')
                ).buildTransaction({
                    "from": send_reward_account.address,
                    "nonce": w3.eth.get_transaction_count(send_reward_account.address),
                    "value": Web3.toWei(0.1, 'ether') * len(address_collection)
                })

                tx = w3.eth.send_transaction(tx_dict)
                logging.info(f"send reward: {tx.hex()}")
                receipt = w3.eth.wait_for_transaction_receipt(tx)
                logging.info(f"status: {receipt['status']}")


    config_logging()
    network = sys.argv[1]

    current_path = pathlib.Path(__file__).resolve()
    config_path = current_path.parent.parent.parent / "config.toml"
    conf = toml.load(config_path)
    load_dotenv(current_path.parent / ".env")

    mock_send = conf['basic']['mock_send']

    send_reward_account: LocalAccount = Account.from_key(os.environ['pk'])

    w3 = Web3(Web3.HTTPProvider(conf['rpc'][network]))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    w3.middleware_onion.add(construct_sign_and_send_raw_middleware(send_reward_account))
    w3.eth.default_account = send_reward_account.address
    w3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
    logging.info(f"{network} connected: {w3.isConnected()}")

    batch_send_contract_address = conf['batchSendContract'][network]
    batch_send_contract_abi = load_abi("batchSend")
    batch_send_contract = w3.eth.contract(batch_send_contract_address, abi=batch_send_contract_abi)

    cross_chain_search_start_block_num = 1899874
    reward_check_search_start_block_num = 2266993
    latest_block_number = w3.eth.block_number

    reward_receiver_address_set = get_send_reward_address_list(
        w3, batch_send_contract_address,
        reward_check_search_start_block_num,
        latest_block_number
    )
    logging.info(f"reward receiver address num: {len(reward_receiver_address_set)}")

    current_check_num = cross_chain_search_start_block_num

    while True:
        check_cross_chain_user()
        time.sleep(5)






