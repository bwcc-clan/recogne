import asyncio
import os
import aiohttp


from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY")
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

abs_cookie_jar = aiohttp.CookieJar()


async def is_logged_in(session: aiohttp.ClientSession):
    url = "https://admin.bwccstats.com/api/is_logged_in"
    async with session.get(url) as resp:
        r = await resp.json()
        print(r)


async def get_logs(session: aiohttp.ClientSession, from_):
    url = "https://admin.bwccstats.com/api/get_historical_logs"
    body = {
        "from": "2023-03-24T22:31:02",
        "limit": 10,
        "time_sort": "asc",
        "output": "json",
    }
    resp = await session.post(url=url, json=body)
    r = await resp.json()
    print(r)


async def login(session: aiohttp.ClientSession):
    url = "https://admin.bwccstats.com/api/login"
    body = {"username": USERNAME, "password": PASSWORD}
    resp = await session.post(url=url, json=body)
    r = await resp.text()
    print(r)


async def main():
    conn = aiohttp.TCPConnector(limit_per_host=100, limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        connector=conn, cookie_jar=abs_cookie_jar
    ) as session:
        await login(session)
        await is_logged_in(session)
        await get_logs(session, "")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
