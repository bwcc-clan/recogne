"""
A tool to download all logs from a CRCON server.
"""

import asyncio
import datetime as dt
import json
import logging
import os

import cattrs
import requests
from attr import frozen
from dotenv import load_dotenv
from json_stream.writer import streamable_list  # type: ignore

logging.basicConfig(level="DEBUG")
logger = logging.getLogger()

load_dotenv()

API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL")

headers = {"Authorization": f"Bearer {API_KEY}"}


@frozen
class LogRecord:
    id: int
    version: int
    creation_time: dt.datetime
    event_time: float
    type: str
    player_name: str
    player1_id: str
    player2_name: str
    player2_id: str
    raw: str
    content: str
    server: str
    weapon: str


converter = cattrs.Converter()
converter.register_unstructure_hook(dt.datetime, lambda dtm: dtm.isoformat())
converter.register_structure_hook(
    dt.datetime, lambda ts, _: dt.datetime.fromisoformat(ts)
)

seen: set[int] = set()


def get_logs(session: requests.Session, start: float):
    url = "https://admin.bwccstats.com/api/get_historical_logs"
    start_date = dt.datetime.fromtimestamp(start) - dt.timedelta(seconds=1)
    logger.debug("Fetching records from %s", start_date.isoformat())
    body = {
        "from": start_date.isoformat(),
        "limit": 5_000,
        "time_sort": "asc",
        "output": "json",
    }
    resp = session.post(url=url, json=body, headers=headers)
    resp.raise_for_status()
    r = resp.json()
    return r


@streamable_list
def log_records():
    start = dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.UTC).timestamp()
    latest: float = start
    loop_count = 0
    with requests.Session() as session:
        session.headers.update(headers)
        while True:
            # Sanity check of loop logoc to prevent running forever
            loop_count += 1
            logger.debug("Loop %d", loop_count)
            if loop_count > 10_000:
                break
            response = get_logs(session, latest)
            if response["failed"] or len(response["result"]) == 0:
                logger.info(f"No more records, failed = {response["failed"]}")
                break
            new_record_count = 0
            for entry in response["result"]:
                log = converter.structure(entry, LogRecord)
                if log.id in seen:
                    logger.debug(
                        "Already seen id %d at time %d", log.id, log.event_time
                    )
                    continue
                seen.add(entry["id"])
                latest = max(log.event_time, latest)
                new_record_count += 1
                yield log
            logger.info(f"Added {new_record_count}/{len(response["result"])} records")
            if new_record_count == 0 and len(response["result"]) > 0:
                # We got some records but they were all duplicate - skip forward a second to bypass them and
                # try again
                latest_dt = dt.datetime.fromtimestamp(latest) + dt.timedelta(seconds=1)
                latest = latest_dt.timestamp()


async def main():
    with open("output.json", "w") as f:
        data = streamable_list([converter.unstructure(i) for i in log_records()])  # type: ignore
        json.dump(data, f)
    logger.info(f"Added {len(seen)} log records")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
