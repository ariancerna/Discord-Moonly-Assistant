import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import requests
from utils.permissions import check_admin

class Licenses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
    
    @app_commands.command(name="send-license", description="Send a license via DM to a user")
    @app_commands.describe(
        user="User who will receive the license",
        product="Product name",
        license="License key"
    )
    async def send_license(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        product: str,
        license: str
    ):
        if not await check_admin(interaction, self.config['roles']['admin_role']):
            return
        
        await interaction.response.send_message(
            "✅ Processing license...",
            ephemeral=True
        )
        
        try:
            # DM to user
            description = (
                f"Este mensaje contiene una licencia que se ha generado para usted.\n"
                f"A continuación verá los detalles de la licencia:\n\n"
                f"👤 Usuario destinatario:\n```{user} ({user.id})```\n"
                f"📦 Producto:\n```{product}```\n"
                f"🔑 Licencia:\n```{license}```"
            )
            
            embed_dm = discord.Embed(
                title="🔐 Has recibido una nueva licencia",
                description=description,
                color=discord.Color.green()
            )
            
            await user.send(embed=embed_dm)
            
            # Confirmation in channel
            embed_ok = discord.Embed(
                title="✅ Licencia enviada correctamente",
                description=(
                    f"Tu licencia ha sido enviada exitosamente por mensaje privado.\n"
                    f"Si tienes alguna pregunta o problema, no dudes en contactarnos.\n\n"
                    f"**👤 Usuario:** ```{user} ({user.id})```\n"
                    f"**📦 Producto:**\n```{product}```"
                ),
                color=discord.Color.green()
            )
            
            await interaction.channel.send(embed=embed_ok)
            
            webhook_url = self.config['webhooks'].get('license_webhook')
            if webhook_url:
                try:
                    data = {
                        "embeds": [
                            {
                                "title": "📦 Licencia Enviada",
                                "thumbnail": {"url": "https://i.imgur.com/p1BgaKk.png"},
                                "color": 0x6c02ff,
                                "fields": [
                                    {
                                        "name": "Enviado por",
                                        "value": f"```{interaction.user} ({interaction.user.id})```",
                                        "inline": False
                                    },
                                    {
                                        "name": "Enviado a",
                                        "value": f"```{user} ({user.id})```",
                                        "inline": False
                                    },
                                    {
                                        "name": "Producto",
                                        "value": f"```{product}```",
                                        "inline": False
                                    },
                                    {
                                        "name": "Licencia",
                                        "value": f"```{license}```",
                                        "inline": False
                                    },
                                    {
                                        "name": "Fecha y hora",
                                        "value": f"```{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}```",
                                        "inline": False
                                    }
                                ]
                            }
                        ]
                    }
                    requests.post(webhook_url, json=data)
                except Exception as log_error:
                    print(f"Error sending to webhook: {log_error}")
        
        except discord.Forbidden:
            embed_error = discord.Embed(
                title="❌ Could not send license",
                description=(
                    f"{user.mention} has direct messages disabled.\n"
                    f"Please ask them to enable DMs to receive the license."
                ),
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=embed_error)
        
        except Exception as e:
            await interaction.followup.send(
                f"❌ Unexpected error: {e}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Licenses(bot))    