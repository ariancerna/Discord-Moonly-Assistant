import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ImageFingerprint:
    filename: str
    content_type: str
    size: int
    sha256: str
    dhash: str
    data: bytes


def hamming_distance(first: str, second: str) -> int:
    """Return the bit distance between two hexadecimal perceptual hashes."""
    if not first or not second or len(first) != len(second):
        return 64
    try:
        return (int(first, 16) ^ int(second, 16)).bit_count()
    except ValueError:
        return 64


def fingerprint_image(
    data: bytes,
    filename: str,
    content_type: str | None = None,
) -> ImageFingerprint:
    """Validate an image and create exact and perceptual fingerprints."""
    if not data:
        raise ValueError("empty image")

    with Image.open(BytesIO(data)) as source:
        source.verify()

    with Image.open(BytesIO(data)) as source:
        normalized = ImageOps.exif_transpose(source).convert("L")
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        pixels = list(normalized.resize((9, 8), resampling).getdata())

    difference = 0
    bit = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            if pixels[offset + column] > pixels[offset + column + 1]:
                difference |= 1 << bit
            bit += 1

    return ImageFingerprint(
        filename=filename,
        content_type=content_type or "image/unknown",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        dhash=f"{difference:016x}",
        data=data,
    )


class AntispamStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS antispam_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    dhash TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT 'spam',
                    source_message_id INTEGER,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, sha256)
                );

                CREATE INDEX IF NOT EXISTS idx_antispam_dhash
                ON antispam_fingerprints(guild_id, dhash);

                CREATE TABLE IF NOT EXISTS antispam_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    attachment_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_antispam_incidents_guild_time
                ON antispam_incidents(guild_id, created_at);
                """
            )

    def add_fingerprint(
        self,
        guild_id: int,
        fingerprint: ImageFingerprint,
        *,
        label: str = "spam",
        source_message_id: int | None = None,
        created_by: int | None = None,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO antispam_fingerprints
                    (guild_id, sha256, dhash, label, source_message_id, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    fingerprint.sha256,
                    fingerprint.dhash,
                    label,
                    source_message_id,
                    created_by,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.rowcount > 0

    def find_match(
        self,
        guild_id: int,
        fingerprint: ImageFingerprint,
        maximum_distance: int,
    ) -> tuple[str | None, int | None]:
        with self._connect() as connection:
            exact = connection.execute(
                """
                SELECT id FROM antispam_fingerprints
                WHERE guild_id = ? AND sha256 = ?
                LIMIT 1
                """,
                (guild_id, fingerprint.sha256),
            ).fetchone()
            if exact:
                return "exact", 0

            rows = connection.execute(
                """
                SELECT dhash FROM antispam_fingerprints
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT 5000
                """,
                (guild_id,),
            ).fetchall()

        nearest = min(
            (hamming_distance(fingerprint.dhash, row["dhash"]) for row in rows),
            default=None,
        )
        if nearest is not None and nearest <= maximum_distance:
            return "visual", nearest
        return None, nearest

    def record_incident(
        self,
        *,
        guild_id: int,
        user_id: int,
        message_id: int,
        channel_id: int,
        score: int,
        action: str,
        reasons: list[str],
        attachment_count: int,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO antispam_incidents
                    (guild_id, user_id, message_id, channel_id, score, action,
                     reasons, attachment_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    message_id,
                    channel_id,
                    score,
                    action,
                    json.dumps(reasons, ensure_ascii=False),
                    attachment_count,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def counts(self, guild_id: int) -> tuple[int, int]:
        with self._connect() as connection:
            fingerprints = connection.execute(
                "SELECT COUNT(*) FROM antispam_fingerprints WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()[0]
            incidents = connection.execute(
                "SELECT COUNT(*) FROM antispam_incidents WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()[0]
        return int(fingerprints), int(incidents)

