import asyncio
import discord
from discord.ext import commands
from utils.logger import logger


class ReminderView(discord.ui.View):
    def __init__(self, website_url: str, label: str, emoji):
        super().__init__(timeout=None)

        self.add_item(discord.ui.Button(
            label=label,
            url=website_url,
            emoji=emoji or None,
            style=discord.ButtonStyle.link
        ))


class Reminder(commands.Cog):
    """Auto-recordatorio: reenvía el embed de reseñas tras cada mensaje de usuario"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.cfg = self.config.get("reminder", {})

        self.channel_id = int(self.cfg.get("channel_id", 0))
        self.delay = float(self.cfg.get("delay", 1))

        # Último recordatorio enviado por canal y tarea pendiente (debounce)
        self.last_messages: dict[int, discord.Message] = {}
        self.pending: dict[int, asyncio.Task] = {}

    async def cog_unload(self):
        for task in self.pending.values():
            task.cancel()
        self.pending.clear()

    def build_embed(self) -> discord.Embed:
        color = self.config["bot"]["embed_color"]
        thumbnail = self.cfg.get("thumbnail", self.config.get("default_avatar"))
        footer_icon = self.cfg.get("footer_icon", self.config.get("default_avatar"))
        vouch_command = self.cfg.get("vouch_command", "/vouch")

        ticket_channel_id = int(self.cfg.get("ticket_channel_id", 0))
        if ticket_channel_id:
            ticket_ref = f"<#{ticket_channel_id}>"
        else:
            ticket_ref = self.cfg.get("ticket_channel_text", "**#🎫・tickets**")

        embed = discord.Embed(color=color)
        embed.description = (
            "## __Deja una reseña__\n"
            f"Por favor, deja un comentario de confianza usando {vouch_command}.\n"
            f"Para realizar una compra, por favor abre un ticket en: {ticket_ref}."
        )

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        embed.set_footer(
            text=self.cfg.get("footer_text", "Moonly - Mensajes Fijados"),
            icon_url=footer_icon
        )

        return embed

    def is_reminder(self, message: discord.Message) -> bool:
        """Comprueba si el mensaje es un recordatorio enviado por este bot"""
        if message.author.id != self.bot.user.id or not message.embeds:
            return False

        footer_text = self.cfg.get("footer_text", "Moonly - Mensajes Fijados")
        return message.embeds[0].footer.text == footer_text

    async def delete_previous(self, channel: discord.TextChannel):
        """Elimina el recordatorio anterior del bot en el canal"""
        previous = self.last_messages.pop(channel.id, None)

        if previous is not None:
            try:
                await previous.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                logger.error(f"❌ No se pudo eliminar el recordatorio anterior: {e}")
            return

        # Sin referencia en memoria (ej. tras un reinicio): buscar en el historial
        try:
            async for msg in channel.history(limit=50):
                if self.is_reminder(msg):
                    await msg.delete()
                    break
        except discord.HTTPException as e:
            logger.error(f"❌ No se pudo limpiar el recordatorio antiguo: {e}")

    async def send_reminder(self, channel: discord.TextChannel):
        try:
            await asyncio.sleep(self.delay)

            await self.delete_previous(channel)

            view = ReminderView(
                website_url=self.cfg.get("website_url", "https://moonlygg.com"),
                label=self.cfg.get("button_label", "Nuestra Página Web"),
                emoji=self.cfg.get("button_emoji")
            )
            self.last_messages[channel.id] = await channel.send(
                embed=self.build_embed(),
                view=view
            )
        except asyncio.CancelledError:
            raise
        except discord.Forbidden:
            logger.error(f"❌ Sin permisos para enviar el recordatorio en #{channel}")
        except discord.HTTPException as e:
            logger.error(f"❌ Error al enviar el recordatorio: {e}")
        finally:
            if self.pending.get(channel.id) is asyncio.current_task():
                self.pending.pop(channel.id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if not self.channel_id or message.channel.id != self.channel_id:
            return
        # Los bots sí cuentan (las reseñas las publica un bot), pero el propio
        # recordatorio no debe volver a dispararse a sí mismo
        if self.is_reminder(message):
            return

        # Si llegan varios mensajes seguidos, solo se envía un recordatorio
        pending = self.pending.pop(message.channel.id, None)
        if pending is not None:
            pending.cancel()

        self.pending[message.channel.id] = asyncio.create_task(
            self.send_reminder(message.channel)
        )


async def setup(bot):
    await bot.add_cog(Reminder(bot))
