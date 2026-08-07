"""Instagram endpoints — same pattern as facebook.py."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.orchestrator import run_agent_task
from api.auth import require_api_key
from api.request_logging import Timer, log_call

router = APIRouter(prefix="/instagram", tags=["instagram"])


class PostRequest(BaseModel):
    topic: str
    instructions: str = ""
    image_url: str = ""  # leave empty to auto-generate an image


class ReelRequest(BaseModel):
    topic: str
    instructions: str = ""
    video_url: str


@router.post("/posts")
async def create_post(body: PostRequest, client_id: str = Depends(require_api_key)):
    with Timer() as t:
        result = await run_agent_task(
            "instagram_post_from_topic",
            {"topic": body.topic, "instructions": body.instructions, "image_url": body.image_url},
            use_browser=False,
        )
    log_call(client_id, "instagram", "post", "/instagram/posts", body.model_dump(),
              result.get("success", False), t.duration_ms, str(result.get("result", "")))
    return result


@router.post("/posts/reel")
async def create_reel(body: ReelRequest, client_id: str = Depends(require_api_key)):
    with Timer() as t:
        result = await run_agent_task(
            "instagram_post_reel",
            {"topic": body.topic, "instructions": body.instructions, "video_url": body.video_url},
            use_browser=False,
            recursion_limit=60,  # video processing needs more polling turns
        )
    log_call(client_id, "instagram", "post_reel", "/instagram/posts/reel", body.model_dump(),
              result.get("success", False), t.duration_ms, str(result.get("result", "")))
    return result


@router.post("/comments/reply-all")
async def reply_to_all_comments(client_id: str = Depends(require_api_key)):
    with Timer() as t:
        result = await run_agent_task("instagram_reply_to_comments", {}, use_browser=False)
    log_call(client_id, "instagram", "reply_comments", "/instagram/comments/reply-all", {},
              result.get("success", False), t.duration_ms, str(result.get("result", "")))
    return result


@router.post("/messages/reply-all")
async def reply_to_all_messages(client_id: str = Depends(require_api_key)):
    with Timer() as t:
        result = await run_agent_task("instagram_reply_to_messages", {}, use_browser=False)
    log_call(client_id, "instagram", "reply_messages", "/instagram/messages/reply-all", {},
              result.get("success", False), t.duration_ms, str(result.get("result", "")))
    return result
