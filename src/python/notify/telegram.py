from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class TelegramProvider:
    bot_token: str
    chat_id: str
    timeout: float = 15.0

    @classmethod
    def from_env(cls) -> Optional["TelegramProvider"]:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat:
            return None
        return cls(bot_token=token, chat_id=chat)
