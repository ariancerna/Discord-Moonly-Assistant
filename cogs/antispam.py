import asyncio
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageOps

from utils.antispam import (
    AntispamStore,
    ImageFingerprint,
    fingerprint_image,
    hamming_distance,
)
from utils.logger import logger
from utils.permissions import check_moderator


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
URL_PATTERN = re.compile(r"https?://|discord\.gg/", re.IGNORECASE)


class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = bot.config
        self.cfg = self.config.get("antispam", {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.alert_channel_id = int(self.cfg.get("alert_channel_id", 1207453755885494352))
        self.delete_threshold = int(self.cfg.get("delete_threshold", 70))
        # Todo mensaje que el filtro elimina recibe también el timeout.
        self.timeout_threshold = self.delete_threshold
        self.timeout_minutes = int(self.cfg.get("timeout_minutes", 10_080))
        self.window_seconds = int(self.cfg.get("window_seconds", 45))
        self.campaign_window_seconds = int(self.cfg.get("campaign_window_seconds", 300))
        self.maximum_image_bytes = int(self.cfg.get("maximum_image_bytes", 10 * 1024 * 1024))
        self.visual_distance = int(self.cfg.get("visual_distance", 8))
        self.exempt_channel_ids = {int(value) for value in self.cfg.get("exempt_channel_ids", [])}
        self.exempt_role_ids = {int(value) for value in self.cfg.get("exempt_role_ids", [])}

        database_path = self.cfg.get("database_path", "data/antispam.db")
        self.store = AntispamStore(database_path)
        self.user_activity: dict[tuple[int, int], deque[tuple[float, int]]] = defaultdict(deque)
        self.recent_images: deque[tuple[float, int, int, str, str]] = deque()
        self.processing_messages: set[int] = set()
        self.analysis_semaphore = asyncio.Semaphore(int(self.cfg.get("analysis_concurrency", 4)))

        Image.MAX_IMAGE_PIXELS = int(self.cfg.get("maximum_image_pixels", 40_000_000))

    @staticmethod
    def _is_image(attachment: discord.Attachment) -> bool:
        content_type = (attachment.content_type or "").lower()
        if content_type.startswith("image/"):
            return True
        filename = attachment.filename.lower()
        return any(filename.endswith(extension) for extension in IMAGE_EXTENSIONS)

    def _is_exempt(self, message: discord.Message) -> bool:
        if message.channel.id in self.exempt_channel_ids:
            return True
        roles = getattr(message.author, "roles", [])
        return any(role.id in self.exempt_role_ids for role in roles)

    async def _analyze_attachment(
        self,
        attachment: discord.Attachment,
    ) -> ImageFingerprint | None:
        if attachment.size > self.maximum_image_bytes:
            return None
        try:
            async with self.analysis_semaphore:
                data = await attachment.read(use_cached=True)
                return await asyncio.to_thread(
                    fingerprint_image,
                    data,
                    attachment.filename,
                    attachment.content_type,
                )
        except (discord.HTTPException, OSError, ValueError) as error:
            logger.warning(f"Anti-spam: no se pudo analizar {attachment.filename}: {error}")
            return None

    def _register_activity(self, message: discord.Message, image_count: int) -> tuple[int, int]:
        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        activity = self.user_activity[key]
        activity.append((now, image_count))
        while activity and now - activity[0][0] > self.window_seconds:
            activity.popleft()
        return len(activity), sum(entry[1] for entry in activity)

    def _campaign_matches(
        self,
        guild_id: int,
        user_id: int,
        fingerprint: ImageFingerprint,
    ) -> tuple[bool, bool, int | None]:
        now = time.monotonic()
        while self.recent_images and now - self.recent_images[0][0] > self.campaign_window_seconds:
            self.recent_images.popleft()

        exact = False
        visual = False
        nearest: int | None = None
        for _, recent_guild, recent_user, recent_sha, recent_dhash in self.recent_images:
            if recent_guild != guild_id or recent_user == user_id:
                continue
            if recent_sha == fingerprint.sha256:
                exact = True
                nearest = 0
                break
            distance = hamming_distance(recent_dhash, fingerprint.dhash)
            nearest = distance if nearest is None else min(nearest, distance)
            if distance <= self.visual_distance:
                visual = True

        return exact, visual, nearest

    def _remember_recent(
        self,
        guild_id: int,
        user_id: int,
        fingerprints: list[ImageFingerprint],
    ) -> None:
        now = time.monotonic()
        for fingerprint in fingerprints:
            self.recent_images.append(
                (now, guild_id, user_id, fingerprint.sha256, fingerprint.dhash)
            )

    def _base_score(
        self,
        message: discord.Message,
        image_count: int,
        message_burst: int,
        image_burst: int,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        if image_count >= 4:
            score += 60
            reasons.append(f"envío masivo de imágenes ({image_count})")
        elif image_count == 3:
            score += 40
            reasons.append("tres imágenes en un solo mensaje")
        elif image_count == 2:
            score += 10

        if image_count >= 3 and not message.content.strip():
            score += 20
            reasons.append("múltiples imágenes sin texto")

        if image_burst >= 8:
            score += 35
            reasons.append(f"ráfaga de {image_burst} imágenes en {self.window_seconds}s")
        elif image_burst >= 5:
            score += 20
            reasons.append(f"actividad rápida: {image_burst} imágenes")

        if message_burst >= 3:
            score += 15
            reasons.append("varios mensajes consecutivos")

        now = discord.utils.utcnow()
        account_age = now - message.author.created_at
        if account_age < timedelta(days=7):
            score += 15
            reasons.append("cuenta creada hace menos de 7 días")
        elif account_age < timedelta(days=30):
            score += 8
            reasons.append("cuenta creada hace menos de 30 días")

        joined_at = getattr(message.author, "joined_at", None)
        if joined_at:
            member_age = now - joined_at
            if member_age < timedelta(days=1):
                score += 12
                reasons.append("miembro nuevo en el servidor")
            elif member_age < timedelta(days=7):
                score += 6

        if URL_PATTERN.search(message.content):
            score += 15
            reasons.append("mensaje con enlace externo")
        if len(message.mentions) + len(message.role_mentions) >= 3 or message.mention_everyone:
            score += 20
            reasons.append("menciones masivas")

        return score, reasons

    async def _score_fingerprints(
        self,
        message: discord.Message,
        fingerprints: list[ImageFingerprint],
        score: int,
        reasons: list[str],
    ) -> tuple[int, list[str], bool]:
        should_learn = False
        known_exact = False
        known_visual_distance: int | None = None
        campaign_exact = False
        campaign_visual_distance: int | None = None

        for fingerprint in fingerprints:
            match_type, distance = await asyncio.to_thread(
                self.store.find_match,
                message.guild.id,
                fingerprint,
                self.visual_distance,
            )
            if match_type == "exact":
                known_exact = True
            elif match_type == "visual" and distance is not None:
                known_visual_distance = (
                    distance
                    if known_visual_distance is None
                    else min(known_visual_distance, distance)
                )

            exact, visual, campaign_distance = self._campaign_matches(
                message.guild.id,
                message.author.id,
                fingerprint,
            )
            campaign_exact = campaign_exact or exact
            if visual and campaign_distance is not None:
                campaign_visual_distance = (
                    campaign_distance
                    if campaign_visual_distance is None
                    else min(campaign_visual_distance, campaign_distance)
                )

        if known_exact:
            score += 100
            reasons.append("coincidencia exacta con una muestra bloqueada")
            should_learn = True
        elif known_visual_distance is not None:
            score += 80
            reasons.append(
                f"imagen visualmente similar a spam conocido (distancia {known_visual_distance})"
            )
            should_learn = True

        if campaign_exact:
            score += 70
            reasons.append("misma imagen publicada recientemente por otra cuenta")
            should_learn = True
        elif campaign_visual_distance is not None:
            score += 45
            reasons.append(
                "campaña visual similar publicada recientemente por otra cuenta"
            )
            should_learn = True

        return min(score, 100), reasons, should_learn

    @staticmethod
    def _build_evidence(fingerprints: list[ImageFingerprint]) -> discord.File | None:
        if not fingerprints:
            return None
        try:
            images: list[Image.Image] = []
            for fingerprint in fingerprints[:4]:
                with Image.open(BytesIO(fingerprint.data)) as source:
                    frame = ImageOps.exif_transpose(source).convert("RGB")
                    frame.thumbnail((420, 260), getattr(Image, "Resampling", Image).LANCZOS)
                    images.append(frame.copy())

            cell_width, cell_height = 440, 280
            columns = 2 if len(images) > 1 else 1
            rows = (len(images) + columns - 1) // columns
            sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#111318")
            draw = ImageDraw.Draw(sheet)
            for index, image in enumerate(images):
                column, row = index % columns, index // columns
                x = column * cell_width + (cell_width - image.width) // 2
                y = row * cell_height + (cell_height - image.height) // 2
                sheet.paste(image, (x, y))
                draw.rectangle(
                    (column * cell_width, row * cell_height, (column + 1) * cell_width - 1,
                     (row + 1) * cell_height - 1),
                    outline="#6c02ff",
                    width=3,
                )

            output = BytesIO()
            sheet.save(output, format="JPEG", quality=82, optimize=True)
            output.seek(0)
            return discord.File(output, filename="antispam-evidence.jpg")
        except (OSError, ValueError):
            return None

    async def _send_alert(
        self,
        message: discord.Message,
        incident_id: int,
        score: int,
        reasons: list[str],
        actions: list[str],
        fingerprints: list[ImageFingerprint],
    ) -> None:
        channel = self.bot.get_channel(self.alert_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.alert_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
                logger.error(f"Anti-spam: canal de alertas inaccesible: {error}")
                return

        embed = discord.Embed(
            title="🚨 Moonly Anti-Spam | Incidente detectado",
            description=(
                f"Se detectó y procesó un mensaje sospechoso de {message.author.mention}."
            ),
            color=discord.Color.red(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=f"{message.author} • {message.author.id}",
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(
            name="📍 Ubicación",
            value=f"{message.channel.mention}\n`{message.channel.id}`",
            inline=True,
        )
        embed.add_field(
            name="🧮 Riesgo",
            value=f"**{score}/100**",
            inline=True,
        )
        embed.add_field(
            name="🖼️ Archivos",
            value=str(len(fingerprints)),
            inline=True,
        )
        embed.add_field(
            name="🔎 Motivos",
            value="\n".join(f"• {reason}" for reason in reasons)[:1024],
            inline=False,
        )
        embed.add_field(
            name="🛡️ Acciones",
            value="\n".join(f"• {action}" for action in actions)[:1024],
            inline=False,
        )

        original_content = message.content.strip()
        if original_content:
            embed.add_field(
                name="💬 Contenido original",
                value=discord.utils.escape_markdown(original_content[:900]),
                inline=False,
            )

        if fingerprints:
            hashes = "\n".join(
                f"`{item.sha256[:12]}` • {item.filename[:45]}" for item in fingerprints[:8]
            )
            embed.add_field(name="🔐 Evidencia", value=hashes[:1024], inline=False)

        embed.set_footer(text=f"Incidente #{incident_id} • Mensaje {message.id}")
        evidence = await asyncio.to_thread(self._build_evidence, fingerprints)
        if evidence:
            embed.set_image(url="attachment://antispam-evidence.jpg")

        try:
            if evidence:
                await channel.send(embed=embed, file=evidence, allowed_mentions=discord.AllowedMentions.none())
            else:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException) as error:
            logger.error(f"Anti-spam: no se pudo enviar la alerta: {error}")

    async def _moderate(
        self,
        message: discord.Message,
        score: int,
        reasons: list[str],
        fingerprints: list[ImageFingerprint],
        should_learn: bool,
    ) -> None:
        actions: list[str] = []
        deleted = False
        try:
            await message.delete()
            deleted = True
            actions.append("mensaje eliminado")
        except discord.NotFound:
            actions.append("el mensaje ya había sido eliminado")
        except (discord.Forbidden, discord.HTTPException) as error:
            actions.append(f"no se pudo eliminar ({type(error).__name__})")

        timed_out = False
        if score >= self.delete_threshold and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(
                    timedelta(minutes=self.timeout_minutes),
                    reason=f"Moonly Anti-Spam: puntuación {score}/100",
                )
                timed_out = True
                timeout_days = self.timeout_minutes / 1440
                timeout_text = (
                    f"{int(timeout_days)} días"
                    if timeout_days.is_integer()
                    else f"{self.timeout_minutes} minutos"
                )
                actions.append(f"timeout automático de {timeout_text}")
            except (discord.Forbidden, discord.HTTPException) as error:
                actions.append(f"no se pudo aplicar timeout ({type(error).__name__})")

        if should_learn or score >= 95:
            learned = 0
            for fingerprint in fingerprints:
                added = await asyncio.to_thread(
                    self.store.add_fingerprint,
                    message.guild.id,
                    fingerprint,
                    label="detección automática",
                    source_message_id=message.id,
                    created_by=self.bot.user.id if self.bot.user else None,
                )
                learned += int(added)
            if learned:
                actions.append(f"{learned} huella(s) añadidas al bloqueo")

        action_code = "+".join(
            value for value, active in (("delete", deleted), ("timeout", timed_out)) if active
        ) or "alert_only"
        incident_id = await asyncio.to_thread(
            self.store.record_incident,
            guild_id=message.guild.id,
            user_id=message.author.id,
            message_id=message.id,
            channel_id=message.channel.id,
            score=score,
            action=action_code,
            reasons=reasons,
            attachment_count=len(fingerprints),
        )
        await self._send_alert(message, incident_id, score, reasons, actions, fingerprints)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.enabled or message.guild is None or message.author.bot:
            return
        if message.id in self.processing_messages or self._is_exempt(message):
            return

        attachments = [item for item in message.attachments if self._is_image(item)]
        if not attachments:
            return

        self.processing_messages.add(message.id)
        try:
            message_burst, image_burst = self._register_activity(message, len(attachments))
            score, reasons = self._base_score(
                message,
                len(attachments),
                message_burst,
                image_burst,
            )
            analyzed = await asyncio.gather(
                *(self._analyze_attachment(attachment) for attachment in attachments[:8])
            )
            fingerprints = [item for item in analyzed if item is not None]

            oversized = sum(item.size > self.maximum_image_bytes for item in attachments)
            if oversized:
                score += 10
                reasons.append(f"{oversized} imagen(es) exceden el límite de análisis")

            score, reasons, should_learn = await self._score_fingerprints(
                message,
                fingerprints,
                score,
                reasons,
            )
            self._remember_recent(message.guild.id, message.author.id, fingerprints)

            if score >= self.delete_threshold:
                await self._moderate(message, score, reasons, fingerprints, should_learn)
        except Exception as error:
            logger.error(f"Anti-spam: error procesando mensaje {message.id}: {error}")
        finally:
            self.processing_messages.discard(message.id)

    @app_commands.command(
        name="antispam-status",
        description="Muestra el estado y las estadísticas del sistema anti-spam",
    )
    @app_commands.guild_only()
    async def antispam_status(self, interaction: discord.Interaction) -> None:
        if not await check_moderator(interaction, self.config["roles"]["moderator_role"]):
            return
        fingerprints, incidents = await asyncio.to_thread(
            self.store.counts,
            interaction.guild_id,
        )
        embed = discord.Embed(
            title="🛡️ Estado de Moonly Anti-Spam",
            color=discord.Color.green() if self.enabled else discord.Color.orange(),
        )
        embed.add_field(name="Estado", value="Activo" if self.enabled else "Desactivado")
        embed.add_field(name="Muestras bloqueadas", value=str(fingerprints))
        embed.add_field(name="Incidentes", value=str(incidents))
        embed.add_field(name="Eliminar desde", value=f"{self.delete_threshold}/100")
        embed.add_field(
            name="Timeout",
            value=f"Desde {self.timeout_threshold}/100 • 7 días",
        )
        embed.add_field(name="Canal de alertas", value=f"<#{self.alert_channel_id}>")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="antispam-muestra",
        description="Añade una imagen confirmada de spam a la protección",
    )
    @app_commands.guild_only()
    @app_commands.describe(imagen="Imagen de spam que debe bloquearse")
    async def antispam_sample(
        self,
        interaction: discord.Interaction,
        imagen: discord.Attachment,
    ) -> None:
        if not await check_moderator(interaction, self.config["roles"]["moderator_role"]):
            return
        if not self._is_image(imagen):
            await interaction.response.send_message("El archivo debe ser una imagen.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        fingerprint = await self._analyze_attachment(imagen)
        if fingerprint is None:
            await interaction.followup.send(
                "No se pudo validar la imagen o excede el límite permitido.",
                ephemeral=True,
            )
            return
        added = await asyncio.to_thread(
            self.store.add_fingerprint,
            interaction.guild_id,
            fingerprint,
            label="muestra manual",
            created_by=interaction.user.id,
        )
        message = "Muestra añadida correctamente." if added else "La imagen ya estaba registrada."
        await interaction.followup.send(
            f"{message}\nHuella: `{fingerprint.sha256[:16]}`",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiSpam(bot))
