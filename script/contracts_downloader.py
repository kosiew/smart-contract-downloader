import argparse
import csv
import json
import math
import os
import sys
from operator import index
from pathlib import Path

import backoff
from etherscan.client import BadRequest, ConnectionRefused, EmptyResponse
from etherscan.contracts import Contract
from tqdm import tqdm


class ContractsDownloadManager:
    def __init__(self, token, addresses="all_contracts.csv", output="data", shard=1, index=0, skip=0, position=0, **kwargs):
        self.token = token
        self.addresses_path = addresses
        self.output_dir = output
        self.shard = shard
        self.index = index
        self.skip = skip
        self.position = position

    def load_not_valid_addresses(self):
        not_valid = []
        if os.path.exists('not_valid.json'):
            with open('not_valid.json') as fd:
                not_valid = json.load(fd)
        return not_valid

    def count_file_lines(self, file_path):
        with open(file_path) as fp:
            return sum(1 for _ in fp)

    def calculate_shard_parameters(self, address_count):
        batch = math.floor(address_count / self.shard)
        start = self.skip + (self.index * batch)
        end = start + batch
        if (self.index + 1) == self.shard:
            end = address_count
        return start, end, batch

    def update_progress_bar(self, pbar, meta):
        pbar.set_postfix(meta)

    def handle_file_download(self, address_path, contract_path, pbar, meta):
        try:
            sourcecode = self.download_contract(address=address_path)
            if not sourcecode[0]['SourceCode']:
                meta["empty"] += 1
            with open(contract_path, 'w') as fd:
                json.dump(sourcecode[0], fd)
        except Exception as e:
            self.not_valid.append(address_path)
            with open('not_valid.json', 'w') as fd:
                json.dump(self.not_valid, fd)
            print(e)
        finally:
            self.update_progress_bar(pbar, meta)

    def download(self):
        self.not_valid = self.load_not_valid_addresses()
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        address_count = self.count_file_lines(self.addresses_path)
        start, end, batch = self.calculate_shard_parameters(address_count)

        with open(self.addresses_path) as fp, tqdm(
            total=batch, position=self.index, desc=f"Shard {self.index+1}/{self.shard}", 
            initial=self.skip) as pbar:
            reader = csv.reader(fp)
            meta = {"token": self.token, "empty": 0}
            for i, line in enumerate(reader, start=1):
                print(f"Processing line {i}")
                if i < start or i > end:
                    continue
                address_path = line[0]
                if address_path in self.not_valid:
                    continue
                contract_path = Path(self.output_dir, f"{address_path}.json")
                print(f"Downloading contract {i}/{address_count}: {address_path}")
                self.handle_file_download(address_path, contract_path, pbar, meta)
                pbar.update(1)

        if self.not_valid:
            with open('not_valid.json', 'w') as fd:
                json.dump(self.not_valid, fd)    

    @backoff.on_exception(backoff.expo,
                          (EmptyResponse, BadRequest, ConnectionRefused),
                          max_tries=8)
    def download_contract(self, address):
        print("Downloading contract: " + address)
        api = Contract(address=address, api_key=self.token)
        sourcecode = api.get_sourcecode()
        return sourcecode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Get source code of contracts')

    parser = argparse.ArgumentParser(
        description='Download contracts from Etherscan.io.')
    parser.add_argument('-t', '--token', metavar='token',
                        type=str, help='Etherscan.io API key.')
    parser.add_argument('-a', '--addresses', metavar='addresses', type=Path, required=False,
                        default="contract_addresses.csv", help='CSV file containing a list of contract addresses to download.')
    parser.add_argument('-o', '--output', metavar='output', type=Path, required=False,
                        default="output", help='the path where the output should be stored.')
    parser.add_argument('--shard', metavar='shard', type=int, required=False,
                        default=1, help='the number of shards to split data in.')
    parser.add_argument('--index', metavar='index', type=int, required='--shard' in sys.argv,
                        default=0, help='the index of the shard to process. Zero indexed.')
    parser.add_argument('--skip', metavar='skip', type=int, required=False,
                        default=0, help='the lines to skip reading from in the address list.')
    args = parser.parse_args()

    token = args.token
    addresses_path = args.addresses.resolve()
    output_dir = args.output.resolve()
    shard = args.shard
    index = args.index
    skip = args.skip

    cdm = ContractsDownloadManager(
        token, addresses_path, output_dir, shard, index, skip)
    cdm.download()
