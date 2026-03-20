#!/usr/bin/env python3
"""
One-time helper to convert a file-based Telethon session to a StringSession.

Run locally (interactive phone/code input required), then copy the output
string into GCP Secret Manager as `telegram-string-session`.

Usage:
  python generate_session.py
"""

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main():
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    phone = os.environ["TELEGRAM_PHONE"]

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone)

    session_string = client.session.save()

    print("\n=== Copy the string below into Secret Manager as telegram-string-session ===\n")
    print(session_string)
    print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
