#!/usr/bin/env python3
"""
Fetch unread messages from all Telegram channels the account is in,
then mark them as read.

Requires: pip install telethon python-dotenv google-cloud-storage
Credentials: https://my.telegram.org -> API development tools

Usage:
  python fetch_messages.py [--channels-only]

  --channels-only   Only show broadcast channels (excludes groups/supergroups)

Credentials are loaded automatically from .env file.
"""

import argparse
import asyncio
import html
import mimetypes
import os
import smtplib
import tempfile
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from google import auth
from google.auth.credentials import Signing
from google.auth.transport import requests as auth_requests
from google.cloud import storage as gcs
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, MessageMediaDocument, MessageMediaPhoto

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch unread Telegram messages.")
    parser.add_argument(
        "--channels-only",
        action="store_true",
        help="Only include broadcast channels (skip groups and supergroups)",
    )
    return parser.parse_args()


def get_credential(env_key):
    value = os.environ.get(env_key)
    if not value:
        raise RuntimeError(f"Required environment variable {env_key} is not set")
    return value


GCS_SIGNED_URL_EXPIRY_DAYS = int(os.environ.get("GCS_SIGNED_URL_EXPIRY_DAYS", "7"))


def _get_gcs_credentials():
    credentials, _ = auth.default()
    if not isinstance(credentials, Signing):
        credentials.refresh(auth_requests.Request())
    return credentials


def upload_to_gcs(local_path: str, bucket_name: str, prefix: str) -> str:
    credentials = _get_gcs_credentials()
    client = gcs.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob_name = f"{prefix}/{Path(local_path).name}"
    blob = bucket.blob(blob_name)
    content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    blob.upload_from_filename(local_path, content_type=content_type)

    signing_kwargs: dict = {"version": "v4"}
    if not isinstance(credentials, Signing):
        signing_kwargs["service_account_email"] = credentials.service_account_email
        signing_kwargs["access_token"] = credentials.token

    return blob.generate_signed_url(
        expiration=timedelta(days=GCS_SIGNED_URL_EXPIRY_DAYS),
        method="GET",
        **signing_kwargs,
    )


def build_html(channel_blocks: list[dict]) -> str:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = sum(len(ch["messages"]) for ch in channel_blocks)

    toc_html = '<nav class="toc"><h2>ערוצים</h2><ul>\n'
    messages_html = ""
    for i, ch in enumerate(channel_blocks):
        anchor = f"ch-{i}"
        name_escaped = html.escape(ch["name"])
        count = len(ch["messages"])
        toc_html += f'<li><a href="#" data-target="{anchor}" onclick="toggle(\'{anchor}\'); return false;">{name_escaped} ({count})</a></li>\n'
        messages_html += f'<div class="channel hidden" id="{anchor}"><h2>{name_escaped} ({count} unread)</h2>\n'
        for m in ch["messages"]:
            media_html = ""
            if m.get("media_path") and m.get("media_type") == "photo":
                media_html = f'<div class="media"><img src="{html.escape(m["media_path"])}" alt="photo"></div>'
            elif m.get("media_path") and m.get("media_type") == "video":
                media_html = f'<div class="media"><video src="{html.escape(m["media_path"])}" controls></video></div>'
            text_part = html.escape(m["text"]) if m["text"] else ""
            messages_html += (
                f'<div class="msg">'
                f'<span class="ts">{html.escape(m["ts"])}</span> '
                f'<span class="sender">{html.escape(m["sender"])}</span>: '
                f'{text_part}'
                f'{media_html}'
                f'</div>\n'
            )
        messages_html += '<div class="read">&#10003; marked as read</div></div>\n'
    toc_html += '</ul></nav>\n'

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telegram Unread Messages</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 800px; margin: 20px auto; padding: 0 16px;
         background: #f5f5f5; color: #1a1a1a; direction: rtl; }}
  h1 {{ border-bottom: 2px solid #0088cc; padding-bottom: 10px; color: #0088cc;
        font-size: clamp(1.2rem, 4vw, 1.8rem); }}
  .toc {{ background: #fff; border-radius: 8px; padding: 16px 20px;
          margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .toc h2 {{ margin: 0 0 10px 0; font-size: 1em; color: #333; }}
  .toc ul {{ margin: 0; padding: 0 16px 0 0; }}
  .toc li {{ padding: 8px 0; }}
  .toc a {{ color: #0088cc; text-decoration: none; cursor: pointer;
            display: inline-block; min-height: 44px; line-height: 44px; }}
  .toc a:hover {{ text-decoration: underline; }}
  .toc a.active {{ font-weight: 700; color: #005f8c; }}
  .channel {{ background: #fff; border-radius: 8px; padding: 16px 20px;
              margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .channel.hidden {{ display: none; }}
  .channel h2 {{ margin: 0 0 12px 0; font-size: 1.1em; color: #333; }}
  .msg {{ padding: 6px 0; border-bottom: 1px solid #eee; line-height: 1.6;
          white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; }}
  .msg:last-of-type {{ border-bottom: none; }}
  .ts {{ color: #888; font-size: 0.85em; direction: ltr; unicode-bidi: embed; }}
  .sender {{ font-weight: 600; color: #0088cc; direction: ltr; unicode-bidi: embed; }}
  .read {{ color: #4caf50; margin-top: 8px; font-size: 0.9em; }}
  .media {{ margin-top: 8px; }}
  .media img {{ max-width: 100%; height: auto; border-radius: 6px; }}
  .media video {{ max-width: 100%; height: auto; border-radius: 6px; }}
  .summary {{ color: #666; margin-bottom: 20px; }}
  @media (max-width: 480px) {{
    body {{ margin: 10px auto; padding: 0 10px; }}
    .channel {{ padding: 12px 14px; }}
    .toc {{ padding: 12px 14px; }}
  }}
</style>
</head>
<body>
<h1>Telegram – הודעות שלא נקראו</h1>
<p class="summary">נמצאו {total} הודעות שלא נקראו &middot; {timestamp}</p>
{toc_html}
{messages_html}
<script>
function toggle(id) {{
  document.querySelectorAll('.channel').forEach(function(el) {{
    if (el.id === id && el.classList.contains('hidden')) {{
      el.classList.remove('hidden');
    }} else {{
      el.classList.add('hidden');
    }}
  }});
  document.querySelectorAll('.toc a').forEach(function(a) {{
    if (a.dataset.target === id && !document.getElementById(id).classList.contains('hidden')) {{
      a.classList.add('active');
    }} else {{
      a.classList.remove('active');
    }}
  }});
}}
</script>
</body>
</html>"""


def send_email(subject: str, body: str):
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("NOTIFY_EMAIL", sender)
    print(f"send_email: sender={sender}, recipient={recipient}, password_set={bool(password)}")
    if not sender or not password:
        print("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set, skipping email notification")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            print("send_email: STARTTLS established, logging in...")
            server.login(sender, password)
            print("send_email: login successful, sending...")
            server.sendmail(sender, recipient, msg.as_string())
        print(f"Email notification sent to {recipient}")
    except Exception as e:
        print(f"send_email failed: {e}")


def upload_report_to_gcs(html_content: str, bucket_name: str, prefix: str) -> str:
    client = gcs.Client()
    bucket = client.bucket(bucket_name)
    blob_name = f"{prefix}/report.html"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_content, content_type="text/html")
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


async def fetch_unread_messages(channels_only: bool):
    api_id = int(get_credential("TELEGRAM_API_ID"))
    api_hash = get_credential("TELEGRAM_API_HASH")
    phone = get_credential("TELEGRAM_PHONE")
    session_string = get_credential("TELEGRAM_STRING_SESSION")

    async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
        await client.start(phone=phone)

        dialogs = await client.get_dialogs()

        def is_wanted(dialog):
            entity = dialog.entity
            if channels_only:
                return isinstance(entity, Channel) and entity.broadcast
            return isinstance(entity, (Channel, Chat))

        targets = [d for d in dialogs if is_wanted(d)]
        kind = "broadcast channel(s)" if channels_only else "channel(s)/group(s)"
        print(f"\nScanning {len(targets)} {kind} for unread messages...\n")

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        gcs_bucket = os.environ.get("GCS_BUCKET")
        gcs_prefix = f"telegram/{run_ts}"

        total = 0
        channel_blocks: list[dict] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for dialog in targets:
                if dialog.unread_count == 0:
                    continue

                last_read_id = dialog.dialog.read_inbox_max_id

                messages = []
                async for msg in client.iter_messages(
                    dialog.entity,
                    min_id=last_read_id,
                    reverse=True,
                ):
                    messages.append(msg)

                if not messages:
                    continue

                print(f"── {dialog.name} ({len(messages)} unread) ──")
                block = {"name": dialog.name, "messages": []}
                for msg in messages:
                    sender = getattr(msg.sender, "username", None) or getattr(msg.sender, "first_name", "unknown")
                    ts = msg.date.strftime("%Y-%m-%d %H:%M UTC")
                    text = (msg.text or "").replace("\n", " ")

                    media_url = None
                    media_type = None

                    if isinstance(msg.media, MessageMediaPhoto):
                        media_type = "photo"
                        local_path = str(Path(tmp_dir) / f"{msg.id}.jpg")
                        await client.download_media(msg, file=local_path)
                        media_url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix)
                        os.remove(local_path)
                        print(f"  [{ts}] {sender}: [photo] {text[:150]}")
                    elif isinstance(msg.media, MessageMediaDocument):
                        mime = msg.media.document.mime_type or ""
                        if mime.startswith("video/"):
                            media_type = "video"
                            ext = mime.split("/")[-1].replace("quicktime", "mov")
                            local_path = str(Path(tmp_dir) / f"{msg.id}.{ext}")
                            await client.download_media(msg, file=local_path)
                            media_url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix)
                            os.remove(local_path)
                            print(f"  [{ts}] {sender}: [video] {text[:150]}")
                        elif mime.startswith("image/"):
                            media_type = "photo"
                            ext = mime.split("/")[-1]
                            local_path = str(Path(tmp_dir) / f"{msg.id}.{ext}")
                            await client.download_media(msg, file=local_path)
                            media_url = upload_to_gcs(local_path, gcs_bucket, gcs_prefix)
                            os.remove(local_path)
                            print(f"  [{ts}] {sender}: [image] {text[:150]}")
                        else:
                            if not text:
                                text = f"[{mime or 'file'}]"
                            print(f"  [{ts}] {sender}: {text[:200]}")
                    else:
                        if not text:
                            text = "[no text]"
                        print(f"  [{ts}] {sender}: {text[:200]}")

                    block["messages"].append({
                        "ts": ts,
                        "sender": sender,
                        "text": text,
                        "media_path": media_url,
                        "media_type": media_type,
                    })

                await client.send_read_acknowledge(dialog.entity, messages[-1])
                print(f"  ✓ marked as read\n")
                total += len(messages)
                channel_blocks.append(block)

        print(f"Done. {total} unread message(s) found.")

        html_content = build_html(channel_blocks)
        reports_bucket = os.environ.get("GCS_REPORTS_BUCKET")
        if reports_bucket:
            url = upload_report_to_gcs(html_content, reports_bucket, gcs_prefix)
            print(f"HTML report uploaded to {url}")
            send_email(
                subject=f"Telegram: {total} unread messages",
                body=f"Report: {url}",
            )
        else:
            out_path = f"unread_messages_{run_ts}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"HTML report saved to {out_path}")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(fetch_unread_messages(channels_only=args.channels_only))
