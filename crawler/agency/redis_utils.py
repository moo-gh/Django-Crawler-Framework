import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)

REDIS_HOST = "crawler-redis"
REDIS_PORT = 6379
PENDING_NEWS_DB = 0
DUPLICATE_CHECKER_DB = 1

TRACKED_ARTICLE_FIELDS = (
    "title",
    "info",
    "info2",
    "info3",
    "info4",
    "built",
    "room",
    "description",
)


def _redis_client(db: int) -> redis.StrictRedis:
    return redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db,
        decode_responses=True,
    )


def get_page_pending_news(page_id: int, limit: int = 25) -> list[dict[str, Any]]:
    """Return pending news articles in Redis (db0) for a given page."""
    results = []
    try:
        client = _redis_client(PENDING_NEWS_DB)
        for key in client.scan_iter("links_*", count=200):
            raw = client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in Redis key %s", key)
                continue
            if data.get("page_id") != page_id:
                continue
            data["_redis_key"] = key
            results.append(data)
            if len(results) >= limit:
                break
    except redis.RedisError:
        logger.exception("Failed to read pending news from Redis")
        return []
    return results


def get_agency_duplicate_links(agency_website: str, limit: int = 25) -> dict[str, Any]:
    """Return duplicate-checker entries (db1) for an agency domain."""
    pattern = f"*{agency_website}*"
    links = []
    total = 0
    try:
        client = _redis_client(DUPLICATE_CHECKER_DB)
        for key in client.scan_iter(pattern, count=200):
            total += 1
            if len(links) < limit:
                ttl = client.ttl(key)
                links.append({"link": key, "ttl_seconds": ttl})
    except redis.RedisError:
        logger.exception("Failed to read duplicate checker from Redis")
        return {"total": 0, "links": [], "error": "Could not connect to Redis"}
    return {"total": total, "links": links}


def get_page_redis_cache(page_id: int, agency_website: str) -> dict[str, Any]:
    """Return a summary of Redis state relevant to a Page."""
    pending_news = get_page_pending_news(page_id)
    duplicate_links = get_agency_duplicate_links(agency_website)
    return {
        "pending_news_count": len(pending_news),
        "pending_news": pending_news,
        "duplicate_checker": duplicate_links,
    }
