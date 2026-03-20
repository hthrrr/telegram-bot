#!/usr/bin/env python3
"""
Fetch the latest N messages from each channel (default 10).
Does NOT mark messages as read — safe for testing.

Usage:
  python fetch_latest.py [--channels-only] [--limit 10]
"""

import argparse
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, MessageMediaDocument, MessageMediaPhoto

from fetch_messages import build_html, get_credential, upload_to_gcs

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch latest Telegram messages (test mode).")
    parser.add_argument(
        "--channels-only",
        action="store_true",
        help="Only include broadcast channels (skip groups and supergroups)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent messages per channel (default: 10)",
    )
    return parser.parse_args()


async def download_and_upload(client, msg, tmp_dir, gcs_bucket, gcs_prefix):
    if isinstance(msg.media, MessageMediaPhoto):
        local_path = str(Path(tmp_dir) / f"{msg.id}.jpg")
        await client.download_media(msg, file=local_path)
        url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix) if gcs_bucket else local_path
        return url, "photo"

    if isinstance(msg.media, MessageMediaDocument):
        mime = msg.media.document.mime_type or ""
        if mime.startswith("video/"):
            ext = mime.split("/")[-1].replace("quicktime", "mov")
            local_path = str(Path(tmp_dir) / f"{msg.id}.{ext}")
            await client.download_media(msg, file=local_path)
            url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix) if gcs_bucket else local_path
            return url, "video"
        if mime.startswith("image/"):
            ext = mime.split("/")[-1]
            local_path = str(Path(tmp_dir) / f"{msg.id}.{ext}")
            await client.download_media(msg, file=local_path)
            url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix) if gcs_bucket else local_path
            return url, "photo"

    return None, None


async def fetch_latest(channels_only: bool, limit: int):
    api_id = int(get_credential("TELEGRAM_API_ID"))
    api_hash = get_credential("TELEGRAM_API_HASH")
    phone = get_credential("TELEGRAM_PHONE")

    async with TelegramClient("session", api_id, api_hash) as client:
        await client.start(phone=phone)

        dialogs = await client.get_dialogs()

        def is_wanted(dialog):
            entity = dialog.entity
            if channels_only:
                return isinstance(entity, Channel) and entity.broadcast
            return isinstance(entity, (Channel, Chat))

        targets = [d for d in dialogs if is_wanted(d)]
        kind = "broadcast channel(s)" if channels_only else "channel(s)/group(s)"
        print(f"\nFetching latest {limit} messages from {len(targets)} {kind}...\n")

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        gcs_bucket = os.environ.get("GCS_BUCKET")
        gcs_prefix = f"telegram/{run_ts}"

        channel_blocks: list[dict] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for dialog in targets:
                messages = []
                async for msg in client.iter_messages(dialog.entity, limit=limit):
                    messages.append(msg)
                messages.reverse()

                if not messages:
                    continue

                print(f"── {dialog.name} ({len(messages)} messages) ──")
                block = {"name": dialog.name, "messages": []}

                for msg in messages:
                    sender = getattr(msg.sender, "username", None) or getattr(msg.sender, "first_name", "unknown")
                    ts = msg.date.strftime("%Y-%m-%d %H:%M UTC")
                    text = (msg.text or "").replace("\n", " ")

                    media_url, media_type = await download_and_upload(
                        client, msg, tmp_dir, gcs_bucket, gcs_prefix
                    )

                    if media_type:
                        print(f"  [{ts}] {sender}: [{media_type}] {text[:150]}")
                    else:
                        if not text:
                            text = "[no text]"
                        print(f"  [{ts}] {sender}: {text[:200]}")

                    block["messages"].append({
                        "ts": ts,
                        "sender": sender,
                        "text": text[:200],
                        "media_path": media_url,
                        "media_type": media_type,
                    })

                channel_blocks.append(block)
                print()

        total = sum(len(ch["messages"]) for ch in channel_blocks)
        print(f"Done. {total} message(s) fetched from {len(channel_blocks)} channels.")

        if channel_blocks:
            out_path = f"latest_messages_{run_ts}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(build_html(channel_blocks))
            print(f"HTML report saved to {out_path}")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(fetch_latest(channels_only=args.channels_only, limit=args.limit))
