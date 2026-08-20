import discord
from discord import app_commands
from discord.ext import commands
import requests

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        latency = self.bot.latency * 1000

        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Bot latency: **{latency:.2f}ms**",
            color=self.config['bot']['embed_color']
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="convert", description="Convert currency from one to another")
    @app_commands.describe(
        amount="Amount to convert",
        from_currency="Currency to convert from (e.g., USD)",
        to_currency="Currency to convert to (e.g., PEN)"
    )
    async def convert(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_currency: str,
        to_currency: str
    ):
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"

        try:
            response = requests.get(url)
            data = response.json()

            if 'error' in data:
                await interaction.response.send_message(
                    f"❌ Error: {data['error']}",
                    ephemeral=True
                )
                return

            rate = data['rates'].get(to_currency.upper())

            if rate is None:
                await interaction.response.send_message(
                    "❌ Currency not found.",
                    ephemeral=True
                )
                return

            converted_amount = amount * rate

            embed = discord.Embed(
                title="💱 Conversión de divisas",
                color=self.config['bot']['embed_color']
            )

            embed.add_field(
                name="De",
                value=f"`{amount:.2f} {from_currency.upper()}`",
                inline=True
            )

            embed.add_field(
                name="A",
                value=f"`{converted_amount:.2f} {to_currency.upper()}`",
                inline=True
            )

            embed.add_field(
                name="Tasa de cambio",
                value=f"`1 {from_currency.upper()} = {rate:.4f} {to_currency.upper()}`",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Utility(bot))
