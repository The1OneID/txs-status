import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pprint import pprint

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import settings
from db_manager import DBManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

FETCHING_INTERVAL_IN_SEC = settings.FETCHING_INTERVAL_IN_SEC


class TransactionFetcher:
    GRAPHQL_ENDPOINT = settings.GRAPHQL_ENDPOINT
    RPC_TXS_BY_LEDGER_ENDPOINT = settings.RPC_TXS_BY_LEDGER_ENDPOINT
    TXS_LIMIT_PER_PAGE = settings.TXS_LIMIT_PER_PAGE
    MAX_RETRIES = settings.MAX_RETRIES
    RETRY_BACKOFF = settings.RETRY_BACKOFF
    MAX_THREADS = settings.MAX_THREADS
    MAX_TXS_AGE_IN_DAYS = settings.MAX_TXS_AGE_IN_DAYS
    MIN_TX_AMOUNT = settings.MIN_TX_AMOUNT
    CONNECTION_POOL_SIZE = settings.CONNECTION_POOL_SIZE

    def __init__(self):
        self.__txs_details = {}
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(
            max_retries=retries, pool_connections=self.CONNECTION_POOL_SIZE, pool_maxsize=self.CONNECTION_POOL_SIZE
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.graphql_headers = {
            "Accept": "*/*",
            "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8,eu;q=0.7",
            "Content-Type": "application/json",
            "Sec-CH-UA": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

    def is_timestamp_within_range(self, timestamp_microseconds):
        timestamp_seconds = timestamp_microseconds / 1_000_000
        timestamp_datetime = datetime.fromtimestamp(timestamp_seconds, timezone.utc)
        current_datetime = datetime.now(timezone.utc)
        x_days_ago = current_datetime - timedelta(days=self.MAX_TXS_AGE_IN_DAYS)
        return timestamp_datetime >= x_days_ago

    def request_with_retry(self, url, method="GET", json=None):
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logging.info(f"Attempting request to URL: {url}, Attempt: {attempt + 1}")
                response = self.session.request(method, url, json=json, headers=self.graphql_headers if json else None)
                response.raise_for_status()
                r = response.json()
                if "graphql" in url and r.get("data") is None:
                    raise requests.exceptions.HTTPError(f"Request {json} resulted in {r}")
                return r
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (429,) or 500 <= e.response.status_code < 600:
                    if attempt < self.MAX_RETRIES:
                        wait_time = self.RETRY_BACKOFF**attempt
                        logging.warning(f"Request {url} failed, retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                logging.error(f"Request failed after {attempt + 1} attempts: {str(e)}")
                raise
        raise Exception(f"Max retries reached for {url}")

    def query_transactions_with_retry(self, offset=0, limit=100):
        body = {
            "operationName": "GetUserTransactions",
            "variables": {"limit": limit, "offset": offset},
            "query": """query GetUserTransactions($limit: Int!, $offset: Int!) {
                userTransactions(limit: $limit, offset: $offset, order: "DESC") {
                    size
                    items {
                        version
                        sender
                        moduleAddress
                        moduleName
                        functionName
                        timestamp
                        success
                        hash
                        __typename
                    }
                    __typename
                }
            }""",
        }
        r = self.request_with_retry(self.GRAPHQL_ENDPOINT, "POST", json=body)
        return r["data"]["userTransactions"]

    def query_transaction_detail(self, tx):
        endpoint = f"{self.RPC_TXS_BY_LEDGER_ENDPOINT}{tx['version']}"
        response_data = self.request_with_retry(endpoint)
        return {
            "hash": response_data["hash"],
            "sender": response_data["sender"],
            "receiver": response_data["payload"]["arguments"][0].lower(),
            "amount": response_data["payload"]["arguments"][1],
            "ledger_version": tx["version"],
            "ledger_timestamp": tx["timestamp"],
        }

    def normalize_txs_hash(self, txs_hash):
        tx_hash = txs_hash.lower()
        if not txs_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return tx_hash

    def __get_transaction_detail_from_cache(self, txs_hash):
        txs_hash = self.normalize_txs_hash(txs_hash)
        return self.__txs_details.get(txs_hash)

    def fetch_transactions(self):
        total_txs = self.query_transactions_with_retry(0, 1)["size"]
        total_pages = math.ceil(total_txs / self.TXS_LIMIT_PER_PAGE)
        all_transactions = []

        with ThreadPoolExecutor(max_workers=self.MAX_THREADS) as executor:
            futures = [
                executor.submit(
                    self.query_transactions_with_retry, page * self.TXS_LIMIT_PER_PAGE, self.TXS_LIMIT_PER_PAGE
                )
                for page in range(total_pages)
            ]
            num_ignored_txs = 0
            total_txs = 0
            for i, future in enumerate(as_completed(futures)):
                data = future.result()
                tx_metadata = data["items"][0]
                if not (
                    tx_metadata["functionName"] == "transfer"
                    and tx_metadata["success"]
                    and self.is_timestamp_within_range(tx_metadata["timestamp"])
                ):
                    num_ignored_txs += 1
                    logging.info(f"Ignored txs: {num_ignored_txs}")
                    continue
                all_transactions.extend(data["items"])
                logging.info(f"Page requests: {i + 1}/{total_pages}")
            total_txs += len(all_transactions)
            logging.info(f"Total txs: {total_txs}")

        relevant_transactions = [
            tx
            for tx in all_transactions
            if tx["functionName"] == "transfer" and self.is_timestamp_within_range(tx["timestamp"])
        ]
        detailed_transactions = []
        with ThreadPoolExecutor(max_workers=self.MAX_THREADS) as executor:
            futures = []
            for tx in relevant_transactions:
                tx_hash = self.normalize_txs_hash(tx["hash"])
                details = self.__get_transaction_detail_from_cache(tx_hash)
                if details is None:
                    futures.append(executor.submit(self.query_transaction_detail, tx))
                else:
                    detailed_transactions.append(details)
            for i, future in enumerate(as_completed(futures)):
                details = future.result()
                detailed_transactions.append(details)
                self.__txs_details[tx_hash] = details
                logging.info(f"Transaction details fetched: {i + 1}/{len(relevant_transactions)}")

        return detailed_transactions


if __name__ == "__main__":
    db = DBManager()
    with DBManager() as m:
        m.db_init()
    detailed_transactions = []
    while True:
        start_time = time.time()
        try:
            fetcher = TransactionFetcher()
            detailed_transactions = fetcher.fetch_transactions()
            logging.info(f"Total detailed transactions: {len(detailed_transactions)}")
            pprint(detailed_transactions[:2])
            logging.info(f"--- {time.time() - start_time} seconds ---")
        except Exception as e:
            logging.error(f"Exception occurred while fetching transactions: {e}")
        start_time = time.time()
        try:
            if detailed_transactions:
                with DBManager() as manager:
                    manager.insert_transactions(detailed_transactions)
            logging.info(f"---Insert data duration: {time.time() - start_time} seconds ---")
        except Exception as e:
            logging.error(f"Exception occurred while saving into DB: {e}")
        time.sleep(FETCHING_INTERVAL_IN_SEC)
        print(" -------------------- || --------------------")
