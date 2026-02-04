import discord
from discord import app_commands
from discord.ext import commands

class Embeds(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.embed_loader = bot.embed_loader
    
    @app_commands.command(name="auto-response", description="Send an embed based on an option")
    @app_commands.describe(option="Choose an embed option")
    async def auto_response(self, interaction: discord.Interaction, option: str):
        if not self.embed_loader:
            await interaction.response.send_message(
                "❌ Embed system is not available.",
                ephemeral=True
            )
            return
        
        embed = self.embed_loader.get_embed(option)
        
        if embed:
            await interaction.response.defer(ephemeral=True)
            try:
                await interaction.channel.send(embed=embed)
                await interaction.followup.send(
                    "✅ Embed sent successfully.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Could not send embed: {str(e)}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Invalid option. Please choose a valid option.",
                ephemeral=True
            )
    
    @auto_response.autocomplete("option")
    async def auto_response_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        if not self.embed_loader:
            return []
        
        display_names = {

            "Binance": "Payments - Binance",
            "PayPal": "Payments - PayPal",
            "Criptomonedas": "Payments - Criptomonedas (LTC/BTC/USDT)",
            "GiftCards": "Payments - Gift Cards (Binance/PSN)",
            "Yape/Plin": "Payments - Transferencia Perú",
            "TransferenciaChile": "Payments - Transferencia Chile",
            "TransferenciaMéxico": "Payments - Transferencia México",
            "DepositoMéxico": "Payments - Depósito México (OXXO)",
            
            "CheteoConsola": "Services - Cheteo Consola",
            "CheteoPC": "Services - Cheteo PC",
            
            "TyCPC": "Terms and Conditions - PC",
            "TyCConsola": "Terms and Conditions - Consola"
        }
        
        options = []
        for key, display_name in display_names.items():
            if self.embed_loader.get_embed(key) and current.lower() in display_name.lower():
                options.append(
                    app_commands.Choice(
                        name=display_name,
                        value=key
                    )
                )
        
        return options[:25]
    
    @app_commands.command(name="warzone-loaders", description="Send a Warzone loader embed")
    @app_commands.describe(option="Choose a Warzone loader option")
    async def warzone_loaders(self, interaction: discord.Interaction, option: str):
        if not self.embed_loader:
            await interaction.response.send_message(
                "❌ Embed system is not available.",
                ephemeral=True
            )
            return
        
        embed = self.embed_loader.get_embed(option)
        
        if embed:
            await interaction.response.defer(ephemeral=True)
            try:
                await interaction.channel.send(embed=embed)
                await interaction.followup.send(
                    "✅ Warzone embed sent successfully.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Could not send embed: {str(e)}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Invalid option. Please choose a valid option.",
                ephemeral=True
            )
    
    @warzone_loaders.autocomplete("option")
    async def warzone_loaders_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        if not self.embed_loader:
            return []
        
        warzone_keys = {
            "AFKTool": "AFK Tool",
            "FecurityChair": "Fecurity Chair",
            "SetupPreparation": "Setup Preparation",
            "UnlockAll": "Unlock All"
        }
        
        options = []
        for key, display in warzone_keys.items():
            if self.embed_loader.get_embed(key) and current.lower() in display.lower():
                options.append(app_commands.Choice(name=display, value=key))
        
        return options
    
    @app_commands.command(name="order-completed", description="Send an order completed embed")
    @app_commands.describe(type="Select recommendation type")
    @app_commands.choices(type=[
        app_commands.Choice(name="PC", value="pc"),
        app_commands.Choice(name="Consola", value="console")
    ])
    async def order_completed(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str]
    ):
        user = interaction.user
        avatar_url = user.avatar.url if user.avatar else self.config['default_avatar']
        
        embed = discord.Embed(
            color=self.config['bot']['embed_color']
        )
        embed.set_thumbnail(url=avatar_url)
        
        if type.value == "pc":
            embed.description = (
                "## 🎮 **__Pedido Completado - PC__**\n\n"
                "> ¡Gracias por confiar en nosotros! Tu pedido ha sido procesado exitosamente. "
                "A continuación, te compartimos algunas recomendaciones importantes para mantener tu cuenta segura.\n\n"
                "**🌟 Déjanos tu opinión**\n"
                "> Te invitamos a dejar una reseña en <#1159643310252638268> usando el comando </vouch:1403090399777784010>.\n\n"
                "**📋 Recomendaciones Importantes**\n"
                "> - **💰 Control de gastos:** Mantén tus gastos diarios por debajo de los 30 millones.\n"
                "> - **🚨 Evita problemas:** No molestes a otros jugadores y previene reportes innecesarios.\n"
                "> - **⛔ Sin inyecciones:** No utilices ningún menú de mods durante los próximos días.\n"
                "> - **💼 Actividad regular:** Realiza trabajos y misiones para que tu cuenta parezca legítima.\n\n"
                "**⚠️ Nota Importante**\n"
                "> Estas recomendaciones son fundamentales para mantener tu cuenta protegida y evitar sanciones."
            )
        elif type.value == "console":
            embed.description = (
                "## 🎮 **__Pedido Completado - Consola__**\n\n"
                "> ¡Tu pedido ha sido procesado exitosamente! Para garantizar la seguridad de tu cuenta, "
                "es crucial que sigas estas recomendaciones al pie de la letra.\n\n"
                "**📋 Recomendaciones Obligatorias**\n\n"
                "**💰 Gestión de dinero**\n"
                "> - No gastes más de **5 millones diarios**\n"
                "> - Esto evita que el sistema detecte movimientos sospechosos\n\n"
                "**🎯 Actividades en el juego**\n"
                "> - Realiza misiones, trabajos y golpes regularmente\n"
                "> - Mezcla el dinero con ganancias \"legítimas\" del juego\n\n"
                "**🔒 Modo de juego**\n"
                "> - Juega únicamente en sesiones privadas o por invitación\n"
                "> - Evita sesiones públicas para prevenir reportes\n\n"
                "**👥 Comportamiento en línea**\n"
                "> - No molestes a otros jugadores ni llames la atención innecesariamente\n"
                "> - Cualquier reporte puede activar revisiones de Rockstar\n\n"
                "**🚗 Ventas de vehículos**\n"
                "> - Vende solo **1 Deluxo por día**\n"
                "> - Espera entre 18-24 horas entre ventas para mantener el 100% del valor\n\n"
                "**⚠️ Recuerda**\n"
                "> La precaución es la clave para mantener tu cuenta segura. Sigue estas indicaciones y disfruta responsablemente.\n"
            )
        
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.channel.send(embed=embed)
            await interaction.followup.send(
                "✅ Embed sent successfully.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not send embed: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Embeds(bot))