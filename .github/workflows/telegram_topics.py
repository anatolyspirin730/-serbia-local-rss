import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession

# Читаем только две выбранные темы
SOURCES = [
    ("Полезная Суботица", -1002110211014, 962),
    ("Суботица", -1002245715379, 1934),
]


async def main():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"].strip()

    # Тест: собираем сообщения за последние 24 часа
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    results = []

    async with TelegramClient(
        StringSession(session), api_id, api_hash
    ) as client:

        for name, group_id, topic_id in SOURCES:
            count = 0

            async for message in client.iter_messages(
                group_id,
                reply_to=topic_id,
                limit=200
            ):
                if message.date < cutoff:
                    break

                if not message.message:
                    continue

                text = message.message.strip()

                if not text:
                    continue

                results.append({
                    "title": text.splitlines()[0][:150],
                    "text": text,
                    "source_name": f"Telegram — {name}",
                    "source_url": (
                        f"https://t.me/c/"
                        f"{str(group_id)[4:]}/{message.id}"
                    ),
                    "published_at": message.date.isoformat(),
                    "message_id": message.id,
                    "topic_id": topic_id
                })

                count += 1

            print(f"{name}: найдено {count} сообщений")

    results.sort(key=lambda item: item["published_at"])

    os.makedirs("feeds", exist_ok=True)

    with open("feeds/telegram_topics.json", "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    print(f"Всего собрано: {len(results)} сообщений")

if __name__ == "__main__":
    asyncio.run(main())
