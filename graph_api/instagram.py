# --------------------------------------------------
# agentic_browser_v2 / graph_api\instagram.py
# --------------------------------------------------

"""
Instagram Business/Creator account actions via Graph API. Requires
instagram_content_publish granted to the token, and IG_BUSINESS_ACCOUNT_ID
set in .env (the IG account's own numeric id, not its @username — find it
via GET /{page-id}?fields=instagram_business_account with your Page token).

IMPORTANT, easy to get bitten by: unlike Facebook Pages (pages.py), which
accept a direct local-file upload, Instagram's media container endpoint
only accepts a PUBLICLY REACHABLE image_url — Meta's servers fetch the
image themselves from that URL. A local file path on your machine won't
work at all. For local files, you need to host them somewhere reachable
first (a real bucket/CDN in production; something like ngrok pointed at a
local static file server works fine for testing).

Publishing is always two calls, not one:
    1. Create a "container" — Meta processes the image/video async
    2. Publish that container once it's done processing
"""

import asyncio
import os

from .client import graph_get, graph_post
from .pages import _page_id


def _ig_user_id() -> str:
    ig_id = os.environ.get("IG_BUSINESS_ACCOUNT_ID")
    if not ig_id:
        raise ValueError("IG_BUSINESS_ACCOUNT_ID is not set in .env")
    return ig_id


async def create_media_container(image_url: str, caption: str = "") -> str:
    """Step 1: tells Meta to fetch and process the image. Returns a
    creation_id — pass this to publish_container() once processing is
    done (see wait_until_ready)."""
    result = await graph_post(
        f"{_ig_user_id()}/media",
        data={"image_url": image_url, "caption": caption},
    )
    return result["id"]


async def get_container_status(creation_id: str) -> str:
    """Returns one of: EXPIRED, ERROR, FINISHED, IN_PROGRESS, PUBLISHED."""
    result = await graph_get(creation_id, params={"fields": "status_code"})
    return result["status_code"]


async def wait_until_ready(creation_id: str, timeout_seconds: int = 60) -> None:
    """Photos usually finish in a couple seconds; videos/Reels can take
    much longer. Polls status_code until FINISHED, or raises on
    ERROR/EXPIRED/timeout."""
    elapsed = 0
    interval = 2
    while elapsed < timeout_seconds:
        status = await get_container_status(creation_id)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Media container {creation_id} failed: {status}")
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Media container {creation_id} did not finish within {timeout_seconds}s")


async def publish_container(creation_id: str) -> dict:
    """Step 2: actually posts the finished container to the feed."""
    return await graph_post(
        f"{_ig_user_id()}/media_publish", data={"creation_id": creation_id}
    )


async def publish_photo(image_url: str, caption: str = "") -> dict:
    """Convenience wrapper: create container -> wait -> publish, in one call."""
    creation_id = await create_media_container(image_url, caption)
    await wait_until_ready(creation_id)
    return await publish_container(creation_id)


async def get_recent_media(limit: int = 10) -> dict:
    """Reads the IG account's recent media (id, caption, timestamp, permalink)."""
    return await graph_get(
        f"{_ig_user_id()}/media",
        params={"limit": limit, "fields": "id,caption,timestamp,permalink"},
    )


async def list_conversations(limit: int = 25) -> dict:
    """Lists recent Instagram DM conversations. Uses the PAGE's id, not
    the IG Business Account id — for the Facebook Login (Page-linked)
    flow this project uses, Instagram messaging rides on the Messenger
    Platform, scoped to the Page, same as messaging.py's Facebook
    conversations. Filter to Instagram-platform conversations via the
    platform param."""
    return await graph_get(
        f"{_page_id()}/conversations",
        params={"limit": limit, "platform": "instagram", "fields": "id,updated_time,unread_count,participants"},
    )


async def get_conversation_messages(conversation_id: str, limit: int = 10) -> dict:
    """Reads recent messages in one Instagram DM conversation."""
    return await graph_get(
        f"{conversation_id}/messages",
        params={"limit": limit, "fields": "id,message,from,created_time"},
    )


async def send_message(recipient_igsid: str, message: str) -> dict:
    """Sends an Instagram DM, as the account — via the Page's /messages
    edge (Messenger Platform), not the IG Business Account's. Meta only
    allows messaging someone who messaged you first, within a 24-hour
    window (7 days for support-only replies after that)."""
    return await graph_post(
        f"{_page_id()}/messages",
        data={
            "recipient": f'{{"id":"{recipient_igsid}"}}',
            "message": f'{{"text":"{message}"}}',
        },
    )


async def list_unreplied_conversations(limit: int = 25) -> list[dict]:
    """Return conversations whose latest message needs a reply.

    The Page Conversations endpoint currently omits ``unread_count`` for
    Instagram conversations (even when it is requested). Treating that
    missing field as zero made every Instagram DM look already handled.
    Instead, inspect the latest message: an incoming latest message needs a
    reply, while an outgoing latest message means this account has already
    replied. This also prevents repeat replies on later scheduler runs.
    """
    conversations = await list_conversations(limit)
    my_ig_id = _ig_user_id()
    unreplied = []
    for convo in conversations.get("data", []):
        messages = await get_conversation_messages(convo["id"], limit=1)
        latest = messages.get("data", [{}])[0]
        sender = latest.get("from", {})

        # ``data`` is newest-first for this endpoint. Do not reply to a
        # conversation whose newest item was sent by this Instagram account.
        if not sender or sender.get("id") == my_ig_id:
            continue

        # Participant IDs in Instagram conversations are IGSIDs, not the
        # Facebook Page ID, so compare them to the IG Business Account ID.
        participants = convo.get("participants", {}).get("data", [])
        participant = next((p for p in participants if p.get("id") == sender.get("id")), {})
        unreplied.append({
            "conversation_id": convo["id"],
            "sender_igsid": sender.get("id", ""),
            "sender_name": sender.get(
                "username",
                sender.get("name", participant.get("username", participant.get("name", "(unknown)"))),
            ),
            "message": latest.get("message", ""),
        })
    return unreplied


async def _own_username() -> str:
    result = await graph_get(_ig_user_id(), params={"fields": "username"})
    return result.get("username", "")


async def get_comments_on_media(media_id: str, limit: int = 25) -> dict:
    """Reads a media's comments, including each comment's direct replies
    (IG only exposes one reply level via this API — no reply-to-reply
    chains like Facebook's comments.py handles)."""
    return await graph_get(
        f"{media_id}/comments",
        params={"limit": limit, "fields": "id,text,username,timestamp,replies{username,text}"},
    )


async def reply_to_comment(comment_id: str, message: str) -> dict:
    """Replies to a specific comment, as the account. Requires
    instagram_manage_comments. Returns {"id": "<new_reply_comment_id>"}."""
    return await graph_post(f"{comment_id}/replies", data={"message": message})


async def list_unreplied_comments(recent_media_limit: int = 50, comments_per_media: int = 25) -> list[dict]:
    """Convenience function: looks at the account's recent media, returns
    comments the account hasn't replied to yet — checked via each
    comment's own replies list against the account's own username.

    Returns [{"media_id", "comment_id", "message", "from_name"}, ...].
    """
    own_username = await _own_username()
    media = await get_recent_media(limit=recent_media_limit)
    unreplied = []
    for item in media.get("data", []):
        comments = await get_comments_on_media(item["id"], limit=comments_per_media)
        for comment in comments.get("data", []):
            replies = comment.get("replies", {}).get("data", [])
            already_replied = any(r.get("username") == own_username for r in replies)
            if not already_replied:
                unreplied.append({
                    "media_id": item["id"],
                    "comment_id": comment["id"],
                    "message": comment.get("text", ""),
                    "from_name": comment.get("username", "(unknown)"),
                })
    return unreplied
