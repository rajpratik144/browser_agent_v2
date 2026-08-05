"""
Post the next topic from content_queue/topics.csv (Graph API only, no
browser). Removes the topic from the CSV on success. Same job the
scheduler runs automatically — this is for a manual one-off run.

    python tasks/graph_api/post_from_queue.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.orchestrator import run_agent_task
from content_queue import csv_queue


async def main():
    topic_row = csv_queue.peek_next_topic()
    if not topic_row:
        print("No topics waiting in content_queue/topics.csv.")
        return

    result = await run_agent_task(
        "facebook_post_from_topic",
        {"topic": topic_row["topic"], "instructions": topic_row["instructions"]},
        verbose=True,
        use_browser=False,
    )
    print("\n" + "=" * 50)
    print(result)

    if result.get("success"):
        csv_queue.remove_next_topic()
        print(f"Removed '{topic_row['topic']}' from the queue.")


if __name__ == "__main__":
    asyncio.run(main())
