import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from database import DB_NAME

class Master(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Garante que apenas quem tem o cargo "Mestre" ou é Admin pode usar
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        role = discord.utils.get(interaction.user.roles, name="Mestre")
        return role is not None or interaction.user.guild_permissions.administrator

    # --- COMANDO: HP GLOBAL ---
    @app_commands.command(name="evento_hp", description="Altera o HP de TODOS os personagens (Dano ou Cura Global).")
    @app_commands.describe(valor="Quantidade (Positivo para curar, Negativo para dano)")
    async def global_hp(self, interaction: discord.Interaction, valor: int):
        await interaction.response.defer() # Evita erro de timeout se tiver muitos players
        
        count = 0
        async with aiosqlite.connect(DB_NAME) as db:
            # Pega todos os personagens
            async with db.execute("SELECT channel_id, hp_current, vigor, hp_bonus FROM characters") as cursor:
                rows = await cursor.fetchall()
            
            for row in rows:
                channel_id, curr, vig, bonus = row
                
                # Recalcula o máximo individual de cada um
                max_hp = 10 + vig + bonus
                
                # Calcula novo HP (sem passar do máximo nem baixar de 0)
                new_hp = max(0, min(curr + valor, max_hp))
                
                # Salva no banco
                await db.execute("UPDATE characters SET hp_current = ? WHERE channel_id = ?", (new_hp, channel_id))
                
                # Notifica no canal do personagem
                channel = self.bot.get_channel(channel_id)
                if channel:
                    action = "recuperou" if valor > 0 else "perdeu"
                    try:
                        # Envia aviso visual
                        emoji = "🩸" if valor < 0 else "💖"
                        await channel.send(f"{emoji} **Evento Global:** Você {action} {abs(valor)} HP. (**{new_hp}**/{max_hp})")
                    except:
                        pass # Ignora se não conseguir enviar mensagem (canal deletado, etc)
                
                count += 1
            
            await db.commit()
        
        await interaction.followup.send(f"✅ **Evento concluído!** HP atualizado para {count} personagens.")

    # --- COMANDO: ESTRESSE GLOBAL ---
    @app_commands.command(name="evento_estresse", description="Altera o Estresse de TODOS os personagens.")
    @app_commands.describe(valor="Quantidade (Positivo aumenta estresse, Negativo alivia)")
    async def global_stress(self, interaction: discord.Interaction, valor: int):
        await interaction.response.defer()
        
        count = 0
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT channel_id, stress_current FROM characters") as cursor:
                rows = await cursor.fetchall()
            
            for row in rows:
                channel_id, curr = row
                new_stress = max(0, min(curr + valor, 10)) # Limite 0 a 10
                
                await db.execute("UPDATE characters SET stress_current = ? WHERE channel_id = ?", (new_stress, channel_id))
                
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = f"🤯 **Evento Global:** Estresse foi para **{new_stress}**/10."
                        if new_stress >= 10: msg += "\n⚠️ **COLAPSO MENTAL IMINENTE!**"
                        await channel.send(msg)
                    except:
                        pass
                count += 1
            
            await db.commit()
            
        await interaction.followup.send(f"✅ **Evento concluído!** Estresse atualizado para {count} personagens.")

    # --- COMANDO: MESTRE DANO (Individual) ---
    # Útil para aplicar dano sem ter que entrar no canal da pessoa
    @app_commands.command(name="mestre_dano", description="Aplica dano/cura a um jogador específico remotamente.")
    async def master_damage(self, interaction: discord.Interaction, jogador: discord.Member, valor: int):
        """Use valor negativo para dano, positivo para cura."""
        async with aiosqlite.connect(DB_NAME) as db:
            # Tenta achar a ficha pelo User ID (pega a primeira que achar)
            async with db.execute("SELECT channel_id, hp_current, vigor, hp_bonus FROM characters WHERE user_id = ? LIMIT 1", (jogador.id,)) as cursor:
                row = await cursor.fetchone()
                
            if not row:
                await interaction.response.send_message(f"❌ Não encontrei ficha para {jogador.mention}.", ephemeral=True)
                return

            channel_id, curr, vig, bonus = row
            max_hp = 10 + vig + bonus
            new_hp = max(0, min(curr + valor, max_hp))
            
            await db.execute("UPDATE characters SET hp_current = ? WHERE channel_id = ?", (new_hp, channel_id))
            await db.commit()
            
            # Notifica o Mestre
            await interaction.response.send_message(f"✅ {jogador.mention} agora tem {new_hp}/{max_hp} HP.")
            
            # Notifica o Jogador no canal dele
            channel = self.bot.get_channel(channel_id)
            if channel:
                action = "Mestre te curou em" if valor > 0 else "Mestre te causou"
                await channel.send(f"⚡ **Intervenção Divina:** {action} {abs(valor)} de dano. (**{new_hp}**/{max_hp})")

async def setup(bot):
    await bot.add_cog(Master(bot))