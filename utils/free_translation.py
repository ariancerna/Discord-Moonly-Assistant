"""Free, cached translations for published Components V2 messages."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional

from deep_translator import GoogleTranslator


class TranslationError(RuntimeError):
    """A safe error that can be shown to a Discord user."""


class TranslationStore:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _create_tables(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS translated_embed_sources (
                    message_id INTEGER PRIMARY KEY,
                    draft_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS translated_embed_cache (
                    message_id INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (message_id, language)
                );

                CREATE TABLE IF NOT EXISTS embed_builder_drafts (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    draft_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                );
                """
            )

    def save_source(self, message_id: int, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO translated_embed_sources (message_id, draft_json)
                VALUES (?, ?)
                ON CONFLICT(message_id) DO UPDATE SET draft_json = excluded.draft_json
                """,
                (message_id, payload),
            )

    def get_source(self, message_id: int) -> Optional[dict]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT draft_json FROM translated_embed_sources WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_translation(self, message_id: int, language: str, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO translated_embed_cache (message_id, language, draft_json)
                VALUES (?, ?, ?)
                ON CONFLICT(message_id, language) DO UPDATE SET draft_json = excluded.draft_json
                """,
                (message_id, language, payload),
            )

    def get_translation(self, message_id: int, language: str) -> Optional[dict]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT draft_json FROM translated_embed_cache
                WHERE message_id = ? AND language = ?
                """,
                (message_id, language),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def clear_translations(self, message_id: int):
        """Discard cached translations after the source publication is edited."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM translated_embed_cache WHERE message_id = ?",
                (message_id,),
            )

    def save_builder_draft(self, guild_id: int, user_id: int, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO embed_builder_drafts (guild_id, user_id, draft_json)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    draft_json = excluded.draft_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, payload),
            )

    def get_builder_draft(self, guild_id: int, user_id: int) -> Optional[dict]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT draft_json FROM embed_builder_drafts
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def delete_builder_draft(self, guild_id: int, user_id: int):
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM embed_builder_drafts
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )


class FreeGoogleTranslationService:
    """Use deep-translator in one worker so small hosts are not overloaded."""

    _protected_pattern = re.compile(
        r"https?://[^\s)>\]]+|<a?:[A-Za-z0-9_~]+:\d+>|<(?:@!?|@&|#)\d+>|</[^:>]+:\d+>"
    )

    def __init__(self, database_path: str = "data/embed_translations.db"):
        self.store = TranslationStore(database_path)
        self._semaphore = asyncio.Semaphore(1)
        self._user_cooldowns: dict[int, float] = {}

    def translation_retry_after(self, user_id: int, cooldown_seconds: float = 8.0) -> float:
        """Rate-limit uncached work while allowing cached translations immediately."""
        now = time.monotonic()
        previous = self._user_cooldowns.get(user_id, 0.0)
        retry_after = cooldown_seconds - (now - previous)
        if retry_after > 0:
            return retry_after
        self._user_cooldowns[user_id] = now
        if len(self._user_cooldowns) > 1000:
            cutoff = now - 3600
            self._user_cooldowns = {
                key: value
                for key, value in self._user_cooldowns.items()
                if value >= cutoff
            }
        return 0.0

    @classmethod
    def _protect(cls, text: str) -> tuple[str, list[str]]:
        protected: list[str] = []

        def replace(match: re.Match[str]) -> str:
            protected.append(match.group(0))
            return f"ZXQKEEP{len(protected) - 1}QXZ"

        return cls._protected_pattern.sub(replace, text), protected

    @staticmethod
    def _restore(text: str, protected: list[str]) -> str:
        for index, value in enumerate(protected):
            placeholder = re.compile(
                rf"ZXQKEEP\s*{index}\s*QXZ",
                re.IGNORECASE,
            )
            text = placeholder.sub(lambda _: value, text)
        return text

    def _translate_sync(self, texts: Iterable[str], target: str) -> list[str]:
        translator = GoogleTranslator(source="auto", target=target)
        values = list(texts)
        results: list[str] = []
        for index, original in enumerate(values):
            if not original.strip():
                results.append(original)
                continue
            protected_text, tokens = self._protect(original)
            try:
                translated = translator.translate(protected_text)
            except Exception as error:
                raise TranslationError(
                    "El traductor gratuito está temporalmente limitado. Inténtalo nuevamente en unos minutos."
                ) from error
            results.append(self._restore(translated or original, tokens))
            if index < len(values) - 1:
                time.sleep(0.25)
        return results

    async def translate_many(self, texts: Iterable[str], target: str) -> list[str]:
        values = list(texts)
        async with self._semaphore:
            return await asyncio.to_thread(self._translate_sync, values, target)
