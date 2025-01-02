import asyncio
import json
import logging
import os
import random
import sys
import time
import timeit

from pyfrost.crypto_utils import Half_N, code_to_pub
from pyfrost.network.dkg import Dkg

from .node_info import NodesInfo


def parse_dkg_json(dkg_path, dkg_name) -> dict:
    with open(dkg_path, "r") as f:
        dkg_info = json.load(f)

    return dkg_info[dkg_name]


async def initiate_dkg(
    total_node_number: int, threshold: int, n: int, dkg_type: str, dkg_name: str
) -> None:
    nodes_info = NodesInfo()
    all_nodes = nodes_info.get_all_nodes(total_node_number)
    dkg = Dkg(nodes_info, default_timeout=50)

    # Random party selection:
    seed = int(time.time())
    random.seed(seed)
    party = random.sample(all_nodes, n)

    # Requesting DKG:
    now = timeit.default_timer()
    dkg_key = await dkg.request_dkg(threshold, party, dkg_type)
    if dkg_type == "ETH":
        is_gt_halfq = code_to_pub(dkg_key["public_key"]).x < Half_N
        while not is_gt_halfq:
            dkg_key = await dkg.request_dkg(threshold, party, dkg_type)
            is_gt_halfq = code_to_pub(dkg_key["public_key"]).x < Half_N
    then = timeit.default_timer()

    logging.info(f"Requesting DKG takes: {then - now} seconds.")
    logging.info(f'The DKG result is {dkg_key["result"]}')

    logging.info(f"DKG key: {dkg_key}")
    dkg_key["threshold"] = threshold
    dkg_key["number_of_nodes"] = n

    dkg_file_path = "./zexporta/dkgs"
    dkg_file_name = "dkgs.json"
    if not os.path.exists(f"{dkg_file_path}/{dkg_file_name}"):
        os.mkdir(dkg_file_path) if not os.path.exists(dkg_file_path) else None
        data = {}
    else:
        with open(f"{dkg_file_path}/{dkg_file_name}", "r") as file:
            data = json.load(file)

    data[dkg_name] = dkg_key
    with open(f"{dkg_file_path}/{dkg_file_name}", "w") as file:
        json.dump(data, file, indent=4)


if __name__ == "__main__":
    file_path = "logs"
    file_name = "test.log"
    log_formatter = logging.Formatter(
        "%(asctime)s - %(message)s",
    )
    root_logger = logging.getLogger()
    if not os.path.exists(file_path):
        os.mkdir(file_path)
    with open(f"{file_path}/{file_name}", "w"):
        pass
    file_handler = logging.FileHandler(f"{file_path}/{file_name}")
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)

    sys.set_int_max_str_digits(0)

    total_node_number = int(sys.argv[1])
    dkg_threshold = int(sys.argv[2])
    num_parties = int(sys.argv[3])
    dkg_type = sys.argv[4]
    dkg_name = sys.argv[5]

    try:
        asyncio.run(
            initiate_dkg(
                total_node_number, dkg_threshold, num_parties, dkg_type, dkg_name
            )
        )
    except KeyboardInterrupt:
        pass
