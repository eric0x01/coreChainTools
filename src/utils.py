import pathlib
import json


def split_list_by_n(list_collection, n):
    for i in range(0, len(list_collection), n):
        yield list_collection[i: i + n]


def load_abi(file_name: str):
    if not file_name.endswith('.json'):
        file_name += '.json'
    current_path = pathlib.Path(__file__).resolve()
    abi_path = current_path.parent / 'abi' / file_name

    with open(abi_path, "r") as f:
        return json.load(f)
