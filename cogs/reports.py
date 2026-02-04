import discord
from discord import app_commands
from discord.ext import commands
from utils.permissions import check_admin

class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
    
    @app_commands.command(name="payment-report", description="Send a payment report for a cheater")
    @app_commands.describe(
        cheater="Select the cheater user",
        payment_methods="Payment methods (separate with ;)",
        paid="Payment status",
        notes="Additional notes (optional)"
    )
    @app_commands.choices(
        paid=[
            app_commands.Choice(name="✅ Paid", value="Pagado"),
            app_commands.Choice(name="⏳ Pending", value="Pendiente"),
            app_commands.Choice(name="❌ Unpaid", value="Sin pagar"),
        ]
    )
    async def payment_report(
        self,
        interaction: discord.Interaction,
        cheater: discord.User,
        payment_methods: str,
        paid: app_commands.Choice[str],
        notes: str = None
    ):
        # Check if user is admin
        if not await check_admin(interaction, self.config['roles']['admin_role']):
            return
        
        # Process payment methods -> separate by ;
        methods_list = [m.strip() for m in payment_methods.split(";") if m.strip()]
        methods_text = "\n".join(f"💳 {m}" for m in methods_list)
        methods_text = f"```\n{methods_text}\n```" if methods_text else "```Not specified```"
        
        # Color based on status
        if paid.value == "Pagado":
            color = discord.Color.green()
            paid_display = "```✅ Pagado```"
        elif paid.value == "Pendiente":
            color = discord.Color.gold()
            paid_display = "```⏳ Pendiente```"
        else:
            color = discord.Color.red()
            paid_display = "```❌ Sin pagar```"
        
        # Build embed
        embed = discord.Embed(
            title="📣 __**Reporte Mensual**__",
            color=color
        )
        embed.add_field(
            name="👤 Chetador",
            value=f"```{cheater} (ID: {cheater.id})```",
            inline=False
        )
        embed.add_field(
            name="💳 Métodos de Pago",
            value=methods_text,
            inline=False
        )
        embed.add_field(
            name="💰 Estado del Pago",
            value=paid_display,
            inline=False
        )
        
        if notes:
            embed.add_field(
                name="📝 Notas",
                value=f"```{notes}```",
                inline=False
            )
        
        embed.set_footer(text="Reporte generado por el sistema - Moonlygg.com")
        
        # Thumbnail (only if has avatar)
        if cheater.avatar:
            embed.set_thumbnail(url=cheater.avatar.url)
        
        # Send embed to the channel
        try:
            await interaction.channel.send(embed=embed)
            await interaction.response.send_message(
                "✅ Report sent successfully to this channel.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"⚠️ Could not send the report: {e}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Reports(bot))