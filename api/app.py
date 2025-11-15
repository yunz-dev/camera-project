import os
import asyncio
import httpx
from typing import List

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
FLICKR_USER = os.getenv("FLICKR_USER")
ADMIN_KEY = os.getenv("ADMIN_KEY")

if not MONGO_URI:
    raise RuntimeError("Missing MONGO_URI in .env")
if not FLICKR_USER:
    raise RuntimeError("Missing FLICKR_USER in .env (must be NSID like 12345@N01)")
if not ADMIN_KEY:
    raise RuntimeError("Missing ADMIN_KEY in .env")


client = AsyncIOMotorClient(MONGO_URI)
db = client["flickr_db"]
photos_col = db["photos"]


app = FastAPI(title="Flickr Photo Sync API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Photo(BaseModel):
    id: str = Field(..., description="Unique Flickr photo ID")
    url: str
    title: str | None = None


class PhotoList(BaseModel):
    photos: List[Photo]


async def upsert_photo(photo: dict):
    """Safely upsert a photo (unique by `id`)."""
    await photos_col.update_one(
        {"id": photo["id"]},
        {"$set": photo},
        upsert=True,
    )


@app.post("/admin/add-photos")
async def admin_add_photos(payload: PhotoList, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    added, updated = 0, 0

    for p in payload.photos:
        existing = await photos_col.find_one({"id": p.id})

        if existing:
            updated += 1
        else:
            added += 1

        await upsert_photo(p.dict())

    return {"status": "ok", "added": added, "updated": updated}


@app.post("/admin/poll")
async def admin_poll(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    await fetch_flickr_photos()
    return {"status": "polled"}


@app.get("/photos")
async def get_photos():
    docs = await photos_col.find().to_list(None)

    # Fix MongoDB ObjectId serialization
    for d in docs:
        d["_id"] = str(d["_id"])

    return docs


async def fetch_flickr_photos():
    """Poll Flickr public feed (20 newest photos)."""

    feed_url = (
        f"https://www.flickr.com/services/feeds/photos_public.gne"
        f"?id={FLICKR_USER}&format=json&nojsoncallback=1"
    )

    async with httpx.AsyncClient() as client:
        r = await client.get(feed_url)
        r.raise_for_status()

        items = r.json().get("items", [])
        for item in items:
            # Use the Flickr link as a stable ID source
            # Example: https://www.flickr.com/photos/12345/67890/
            link_parts = item["link"].rstrip("/").split("/")
            photo_id = link_parts[-1]

            await upsert_photo(
                {
                    "id": photo_id,
                    "url": item["media"]["m"],
                    "title": item.get("title") or None,
                }
            )


async def poll_flickr_forever():
    """Runs forever, polling every 5 minutes."""
    while True:
        try:
            print("Syncing Flickr feed…")
            await fetch_flickr_photos()
            print("Done, sleeping 5 minutes.")
        except Exception as e:
            print("Error during Flickr sync:", e)

        await asyncio.sleep(300)  # 5 minutes


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(poll_flickr_forever())
