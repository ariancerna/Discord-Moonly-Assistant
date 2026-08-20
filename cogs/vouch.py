import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


class VouchDatabase:
    """Small SQLite repository for vouches."""

    def __init__(self, database_path: str):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _reset_sequence(connection: sqlite3.Connection):
        """Make the next vouch follow the highest ID that still exists."""
        max_id = connection.execute("SELECT MAX(id) FROM vouches").fetchone()[0] or 0
        sequence_value = max(max_id, 399)
        cursor = connection.execute(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = 'vouches'",
            (sequence_value,),
        )
        if cursor.rowcount == 0:
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES ('vouches', ?)",
                (sequence_value,),
            )

    def _create_tables(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vouches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    author_id INTEGER NOT NULL,
                    author_name TEXT NOT NULL,
                    author_avatar_url TEXT,
                    author_avatar_path TEXT,
                    review_message TEXT NOT NULL,
                    stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
                    proof_url TEXT,
                    proof_path TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Vouches start at 400. If the latest ones were deleted while the
            # bot was offline, make those trailing numbers available again.
            self._reset_sequence(connection)

    def add_vouch(self, data: dict) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO vouches (
                    guild_id, channel_id, message_id, author_id, author_name,
                    author_avatar_url, review_message, stars, proof_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["guild_id"],
                    data["channel_id"],
                    data.get("message_id"),
                    data["author_id"],
                    data["author_name"],
                    data.get("author_avatar_url"),
                    data["review_message"],
                    data["stars"],
                    data.get("proof_url"),
                    data["created_at"],
                ),
            )
            return cursor.lastrowid

    def set_image_paths(self, vouch_id: int, avatar_path: str | None, proof_path: str | None):
        with self._connect() as connection:
            connection.execute(
                "UPDATE vouches SET author_avatar_path = ?, proof_path = ? WHERE id = ?",
                (avatar_path, proof_path, vouch_id),
            )

    def set_message_id(self, vouch_id: int, message_id: int):
        with self._connect() as connection:
            connection.execute(
                "UPDATE vouches SET message_id = ? WHERE id = ?",
                (message_id, vouch_id),
            )

    def get_vouch(self, vouch_id: int) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM vouches WHERE id = ?", (vouch_id,)
            ).fetchone()

    def get_guild_vouches(self, guild_id: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM vouches WHERE guild_id = ? ORDER BY id ASC", (guild_id,)
            ).fetchall()

    def delete_vouch(self, guild_id: int, vouch_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vouches WHERE guild_id = ? AND id = ?",
                (guild_id, vouch_id),
            ).fetchone()
            if row is None:
                return None

            connection.execute(
                "DELETE FROM vouches WHERE guild_id = ? AND id = ?",
                (guild_id, vouch_id),
            )
            # AUTOINCREMENT normally remembers deleted IDs forever. Reset it
            # inside this transaction so deleting the latest vouch makes that
            # number available to the next one.
            self._reset_sequence(connection)
            return dict(row)


class VouchView(discord.ui.View):
    def __init__(self, review_channel_url: str):
        super().__init__(timeout=None)

        self.add_item(
            discord.ui.Button(
                label="Canal de Reseñas",
                url=review_channel_url,
                emoji="<:PandaDab:1234344971264331836>",
                style=discord.ButtonStyle.link,
            )
        )


class Vouch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        vouch_config = self.config.get("vouch", {})
        self.database = VouchDatabase(vouch_config.get("database_path", "data/vouches.db"))
        self.image_directory = Path(
            vouch_config.get("image_directory", "data/vouch_images")
        )
        self.image_directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _stars(stars: int) -> str:
        return "⭐" * stars

    def _can_manage_vouches(self, interaction: discord.Interaction) -> bool:
        """Allow the server owner and the configured vouch manager role."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False

        if interaction.user.id == interaction.guild.owner_id:
            return True

        manager_role_id = self.config.get("roles", {}).get("vouch_manager_role")
        return bool(
            manager_role_id
            and any(role.id == manager_role_id for role in interaction.user.roles)
        )

    def _build_vouch_embed(self, row: sqlite3.Row, avatar_attachment: str | None = None,
                           proof_attachment: str | None = None) -> discord.Embed:
        color = self.config["bot"]["embed_color"]
        vouch_url = self.config.get("vouch", {}).get(
            "website_url", "https://myvouch.es/moonly"
        )
        embed = discord.Embed(
            description=(
                f"### [¡Nueva reseña creada!]({vouch_url})\n"
                f"{self._stars(row['stars'])}"
            ),
            color=color,
        )

        try:
            embed.timestamp = datetime.strptime(
                row["created_at"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            embed.timestamp = datetime.now(timezone.utc)

        # A full-width field gives a short native gap (roughly half a blank
        # line) between the stars and the review text on every Discord client.
        review_message = row["review_message"] or "\u200b"
        if len(review_message) > 1024:
            review_message = f"{review_message[:1021]}..."
        embed.add_field(name="Vouch:", value=review_message, inline=False)
        embed.add_field(name="Vouch Nº:", value=str(row["id"]), inline=True)
        embed.add_field(
            name="Vouched by:",
            value=f"<@{row['author_id']}>",
            inline=True,
        )
        embed.add_field(name="Vouched at:", value=row["created_at"], inline=True)

        # The customer's avatar is shown as the embed thumbnail.
        avatar_url = (
            f"attachment://{avatar_attachment}"
            if avatar_attachment
            else row["author_avatar_url"]
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        # The uploaded proof is shown as the large image below the embed.
        if proof_attachment:
            embed.set_image(url=f"attachment://{proof_attachment}")
        elif row["proof_url"]:
            embed.set_image(url=row["proof_url"])

        vouch_config = self.config.get("vouch", {})
        embed.set_footer(
            text="© Moonly, All Rights Reserved",
            icon_url=vouch_config.get("footer_icon", self.config.get("default_avatar")),
        )
        return embed

    def _build_vouch_payload(
        self,
        row: sqlite3.Row,
        avatar_path: str | None,
        proof_path: str | None,
    ) -> tuple[discord.Embed, list[discord.File]]:
        """Build fresh attachment objects so a failed send can be retried safely."""
        files = []
        avatar_attachment = None
        proof_attachment = None

        if avatar_path and Path(avatar_path).is_file():
            avatar_attachment = Path(avatar_path).name
            files.append(discord.File(avatar_path, filename=avatar_attachment))

        if proof_path and Path(proof_path).is_file():
            proof_attachment = Path(proof_path).name
            files.append(discord.File(proof_path, filename=proof_attachment))

        embed = self._build_vouch_embed(
            row, avatar_attachment, proof_attachment
        )
        return embed, files

    async def _send_restored_vouch(
        self,
        channel: discord.TextChannel,
        row: sqlite3.Row,
        avatar_path: str | None,
        proof_path: str | None,
    ) -> discord.Message:
        """Send one restored vouch, retrying transient Discord API failures."""
        configured_retries = self.config.get("vouch", {}).get("restore_retries", 3)
        try:
            max_attempts = max(1, min(int(configured_retries), 5))
        except (TypeError, ValueError):
            max_attempts = 3

        for attempt in range(max_attempts):
            embed, files = self._build_vouch_payload(row, avatar_path, proof_path)
            try:
                return await channel.send(embed=embed, files=files)
            except discord.Forbidden:
                raise
            except discord.HTTPException:
                if attempt + 1 >= max_attempts:
                    raise
                # discord.py already honors 429 Retry-After responses. This
                # backoff also covers temporary gateway/API failures.
                await asyncio.sleep(min(2 ** (attempt + 1), 8))

        raise RuntimeError("Could not send restored vouch")

    async def _download_file(self, url: str, destination: Path) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    destination.write_bytes(await response.read())
                    return True
        except (aiohttp.ClientError, OSError):
            return False

    async def _download_vouch_images(
        self,
        vouch_id: int,
        user: discord.User | discord.Member,
        proof: discord.Attachment | None,
    ) -> tuple[str | None, str | None]:
        guild_directory = self.image_directory / str(user.guild.id if isinstance(user, discord.Member) else 0)
        guild_directory.mkdir(parents=True, exist_ok=True)

        avatar_file = guild_directory / f"vouch_{vouch_id}_avatar.png"
        avatar_saved = await self._download_file(
            str(user.display_avatar.replace(format="png", size=256).url), avatar_file
        )

        proof_file = None
        proof_saved = False
        if proof:
            extension = Path(proof.filename).suffix.lower() or ".bin"
            proof_file = guild_directory / f"vouch_{vouch_id}_proof{extension}"
            proof_saved = await self._download_file(proof.url, proof_file)

        return (
            str(avatar_file) if avatar_saved else None,
            str(proof_file) if proof_saved and proof_file else None,
        )

    async def _restore_missing_image_paths(self, row: sqlite3.Row) -> tuple[str | None, str | None]:
        """Re-download images if the local files were moved or deleted."""
        guild_directory = self.image_directory / str(row["guild_id"])
        guild_directory.mkdir(parents=True, exist_ok=True)

        avatar_path = row["author_avatar_path"]
        if (
            not avatar_path or not Path(avatar_path).is_file()
        ) and row["author_avatar_url"]:
            avatar_file = guild_directory / f"vouch_{row['id']}_avatar.png"
            if await self._download_file(row["author_avatar_url"], avatar_file):
                avatar_path = str(avatar_file)

        proof_path = row["proof_path"]
        if not proof_path or not Path(proof_path).is_file():
            if row["proof_url"]:
                suffix = Path(urlparse(row["proof_url"]).path).suffix.lower() or ".png"
                proof_file = guild_directory / f"vouch_{row['id']}_proof{suffix}"
                if await self._download_file(row["proof_url"], proof_file):
                    proof_path = str(proof_file)

        if avatar_path != row["author_avatar_path"] or proof_path != row["proof_path"]:
            await asyncio.to_thread(
                self.database.set_image_paths, row["id"], avatar_path, proof_path
            )

        return avatar_path, proof_path

    @app_commands.command(
        name="vouch",
        description="Create a new vouch for this Discord server!",
    )
    @app_commands.describe(
        message="Your review or comment",
        stars="Choose a rating from 1 to 5 stars",
        proof="Optional image showing your purchase or result",
    )
    @app_commands.choices(
        stars=[
            app_commands.Choice(name="⭐", value=1),
            app_commands.Choice(name="⭐⭐", value=2),
            app_commands.Choice(name="⭐⭐⭐", value=3),
            app_commands.Choice(name="⭐⭐⭐⭐", value=4),
            app_commands.Choice(name="⭐⭐⭐⭐⭐", value=5),
        ]
    )
    async def vouch_command(
        self,
        interaction: discord.Interaction,
        message: str,
        stars: app_commands.Choice[int],
        proof: discord.Attachment | None = None,
    ):
        """Create a review. Only members with the configured client role may use it."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Este comando solo se puede usar dentro de un servidor.", ephemeral=True
            )
            return

        if proof and proof.content_type and not proof.content_type.startswith("image/"):
            await interaction.response.send_message(
                "❌ La prueba debe ser una imagen.", ephemeral=True
            )
            return

        client_role_id = self.config.get("roles", {}).get("client_role")
        if not client_role_id or not any(role.id == client_role_id for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ Solo los clientes pueden dejar un vouch.", ephemeral=True
            )
            return

        await interaction.response.defer()

        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        vouch_id = await asyncio.to_thread(
            self.database.add_vouch,
            {
                "guild_id": interaction.guild.id,
                "channel_id": interaction.channel_id,
                "author_id": interaction.user.id,
                "author_name": str(interaction.user),
                "author_avatar_url": str(interaction.user.display_avatar.url),
                "review_message": message,
                "stars": stars.value,
                "proof_url": proof.url if proof else None,
                "created_at": created_at,
            },
        )

        avatar_path, proof_path = await self._download_vouch_images(
            vouch_id, interaction.user, proof
        )
        await asyncio.to_thread(
            self.database.set_image_paths, vouch_id, avatar_path, proof_path
        )

        row = await asyncio.to_thread(self.database.get_vouch, vouch_id)
        if row is None:
            await interaction.followup.send(
                "❌ No se pudo leer el vouch recién guardado.", ephemeral=True
            )
            return
        embed, files = self._build_vouch_payload(row, avatar_path, proof_path)
        sent_message = await interaction.followup.send(embed=embed, files=files, wait=True)
        if sent_message:
            await asyncio.to_thread(
                self.database.set_message_id, vouch_id, sent_message.id
            )

    @app_commands.command(
        name="restore-vouches",
        description="Restore all saved vouches in this server.",
    )
    @app_commands.describe(channel="Channel where the vouches will be restored")
    async def restore_vouches_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        """Restore vouches from SQLite for the owner or authorized role."""
        if not self._can_manage_vouches(interaction):
            await interaction.response.send_message(
                "❌ No tienes el rol autorizado para restaurar los vouches.",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Selecciona un canal de texto válido.", ephemeral=True
            )
            return

        rows = await asyncio.to_thread(
            self.database.get_guild_vouches, interaction.guild.id
        )
        if not rows:
            await interaction.response.send_message(
                "ℹ️ No hay vouches guardados para este servidor.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        restored = 0
        failed = 0
        configured_delay = self.config.get("vouch", {}).get("restore_delay", 1.0)
        try:
            restore_delay = max(0.0, min(float(configured_delay), 10.0))
        except (TypeError, ValueError):
            restore_delay = 1.0

        for index, row in enumerate(rows):
            avatar_path, proof_path = await self._restore_missing_image_paths(row)
            try:
                await self._send_restored_vouch(
                    target_channel, row, avatar_path, proof_path
                )
                restored += 1
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ No puedo enviar embeds o adjuntar imágenes en ese canal. "
                    "Revisa mis permisos.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                failed += 1

            if restore_delay and index + 1 < len(rows):
                await asyncio.sleep(restore_delay)

        result = f"✅ Se restauraron {restored} vouch(s) en {target_channel.mention}."
        if failed:
            result += f"\n⚠️ {failed} vouch(s) no se pudieron enviar después de los reintentos."
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(
        name="delete-vouch",
        description="Delete a vouch from the database and remove its saved images.",
    )
    @app_commands.describe(vouch_id="The Vouch Nº to delete")
    async def delete_vouch_command(
        self,
        interaction: discord.Interaction,
        vouch_id: int,
    ):
        """Delete a vouch for the owner or authorized role."""
        if not self._can_manage_vouches(interaction):
            await interaction.response.send_message(
                "❌ No tienes el rol autorizado para eliminar vouches.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await asyncio.to_thread(
            self.database.delete_vouch, interaction.guild.id, vouch_id
        )
        if deleted is None:
            await interaction.followup.send(
                f"❌ No existe el vouch Nº {vouch_id} en este servidor.",
                ephemeral=True,
            )
            return

        removed_images = 0
        for image_key in ("author_avatar_path", "proof_path"):
            image_path = deleted.get(image_key)
            if not image_path:
                continue

            candidate = Path(image_path)
            try:
                # Only remove files inside the configured vouch image folder.
                candidate.resolve().relative_to(self.image_directory.resolve())
                if candidate.is_file():
                    candidate.unlink()
                    removed_images += 1
            except (OSError, ValueError):
                continue

        await interaction.followup.send(
            f"✅ Se eliminó el vouch Nº {vouch_id} y {removed_images} imagen(es) guardada(s).",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Keep the legacy comma command separate from /vouch."""
        if message.author.bot:
            return
        if message.content.strip().lower() != ",vouch":
            return

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        vouch_cfg = self.config.get("vouch", {})
        color = self.config["bot"]["embed_color"]
        thumbnail = vouch_cfg.get("thumbnail", self.config.get("default_avatar"))
        review_channel_url = vouch_cfg.get("review_channel_url", "https://discord.com")
        footer_icon = vouch_cfg.get("footer_icon", self.config.get("default_avatar"))

        embed = discord.Embed(color=color)
        embed.description = (
            "# __Pedido Completado__\n"
            "> Gracias por convertirte en uno de nuestros clientes, apreciamos enormemente "
            "que hayas decidido comprar con nosotros y esperamos verte nuevamente.\n"
            "# __Déjanos tu Opinión__\n"
            "> Realmente esperamos que puedas dejar algún comentario, esto ayuda a apoyar "
            "nuestro crecimiento. Puedes hacerlo usando </vouch:1403090399777784010>"
        )

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        embed.set_footer(
            text="Moonly. Todos los derechos reservados.",
            icon_url=footer_icon,
        )

        await message.channel.send(embed=embed, view=VouchView(review_channel_url))


async def setup(bot):
    await bot.add_cog(Vouch(bot))
