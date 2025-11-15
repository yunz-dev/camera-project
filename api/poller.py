import os
import time
import json
import requests
import asyncio
from motor.motor_asyncio import AsyncIOMotorCollection

FLICKR_USER_ID = os.getenv("FLICKR_USER_ID")
FEED_URL = f"https://www.flickr.com/services/feeds/photos_public.gne?id={
    FLICKR_USER_ID
}&format=json&nojsoncallback=1"

POLL_INTERVAL = 300  # 5 minutes


def extract_photo_id(link: str) -> str:
    return link.rstrip("/").split("/")[-1]


async def poll_feed(photos: AsyncIOMotorCollection):
    print("[Poller] Fetching Flickr feed...")

    r = requests.get(FEED_URL, timeout=10)
    data = r.json()

    new_count = 0

    for item in data["items"]:
        link = item["link"]
        photo_id = extract_photo_id(link)

        exists = await photos.find_one({"_id": photo_id})
        if exists:
            continue

        await photos.insert_one(
            {
                "_id": photo_id,
                "title": item.get("title", ""),
                "link": link,
                "published": item.get("published", ""),
                "json_data": item,
            }
        )

        new_count += 1
        print(f"[Poller] Added new photo {photo_id}")

    print(f"[Poller] Done. New photos added: {new_count}")


async def start_polling(photos: AsyncIOMotorCollection):
    while True:
        try:
            await poll_feed(photos)
        except Exception as e:
            print("[Poller] Error:", e)

        await asyncio.sleep(POLL_INTERVAL)
