import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import random
from database import DB_NAME

class Combat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_mestre(self, interaction: discord.Interaction) -> bool:
        role = discord.utils.get(interaction.user.roles, name="Mestre")
        return role is not None or interaction.user.guild_permissions.administrator

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.is_mestre(interaction):
            await interaction.response.send_message("⛔ Ferramenta exclusiva do Mestre.", ephemeral=True)
            return False
        return True

    async def combatant_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT name FROM combatants WHERE name LIKE ? LIMIT 25", (f"%{current}%",)) as cursor:
                rows = await cursor.fetchall()
        return [app_commands.Choice(name=r[0], value=r[0]) for r in rows]

    # --- INÍCIO ---

    @app_commands.command(name="batalha_iniciar", description="Cria o Rastreador de Mestre.")
    async def start_battle(self, interaction: discord.Interaction):
        guild = interaction.guild
        cat_name = "ÁREA DO MESTRE"
        category = discord.utils.get(guild.categories, name=cat_name)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        if not category: category = await guild.create_category(cat_name, overwrites=overwrites)

        try:
            channel = await guild.create_text_channel("campo-de-batalha", overwrites=overwrites, category=category)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM combat_state")
            await db.execute("DELETE FROM combatants")
            await db.execute("DELETE FROM combat_effects")
            await db.execute("INSERT INTO combat_state (channel_id, round, turn_index) VALUES (?, 1, 0)", (channel.id,))
            await db.commit()

        await interaction.response.send_message(f"✅ Rastreador criado: {channel.mention}", ephemeral=True)
        
        embed = discord.Embed(title="⚔️ RASTREADOR DE COMBATE", description="Iniciativa Mista (Maior age primeiro).", color=0x2b2d31)
        msg = await channel.send(embed=embed)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE combat_state SET message_id = ?", (msg.id,))
            await db.commit()

    @app_commands.command(name="batalha_fim", description="Encerra o combate.")
    async def end_battle(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT channel_id FROM combat_state") as cursor:
                if row := await cursor.fetchone():
                    if ch := self.bot.get_channel(row[0]): await ch.delete()
            await db.execute("DELETE FROM combat_state")
            await db.execute("DELETE FROM combatants")
            await db.execute("DELETE FROM combat_effects")
            await db.commit()
        try: await interaction.response.send_message("🏳️ Fim.", ephemeral=True)
        except: pass

    # --- GERENCIAMENTO (COM DT E INICIATIVA REAL) ---

    @app_commands.command(name="add_jogador", description="Adiciona jogador (DT = 8 + AGI).")
    async def add_player(self, interaction: discord.Interaction, jogador: discord.Member, iniciativa: int):
        async with aiosqlite.connect(DB_NAME) as db:
            # Pega Agilidade para calcular a DT (Defesa)
            async with db.execute("SELECT id, name, hp_current, vigor, hp_bonus, agilidade FROM characters WHERE user_id = ? LIMIT 1", (jogador.id,)) as cur:
                char = await cur.fetchone()
                if not char: return await interaction.response.send_message(f"❌ {jogador.display_name} sem ficha.", ephemeral=True)
                cid, name, hp, vig, bonus, agi = char
                max_hp = 10 + vig + bonus
                
                # DT do Jogador = 8 + Agilidade
                player_dt = 8 + agi

            await db.execute("""
                INSERT INTO combatants (name, team, initiative, hp_current, hp_max, dt, original_char_id) 
                VALUES (?, 'JOGADOR', ?, ?, ?, ?, ?)
            """, (name, iniciativa, hp, max_hp, player_dt, cid))
            await db.commit()

        await interaction.response.send_message(f"👤 **{name}** (Inic {iniciativa} | DT {player_dt}) adicionado.", ephemeral=True)
        await self.update_dashboard(interaction)

    @app_commands.command(name="add_todos", description="Adiciona TODOS (Iniciativa Auto | DT Auto).")
    async def add_all_players(self, interaction: discord.Interaction):
        added_names = []
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id, name, hp_current, vigor, hp_bonus, agilidade FROM characters") as cursor:
                chars = await cursor.fetchall()
            
            if not chars: return await interaction.response.send_message("❌ Sem fichas.", ephemeral=True)

            for char in chars:
                cid, name, hp, vig, bonus, agi = char
                max_hp = 10 + vig + bonus
                player_dt = 8 + agi
                
                # Check duplicidade
                async with db.execute("SELECT id FROM combatants WHERE original_char_id = ?", (cid,)) as cur_check:
                    if await cur_check.fetchone(): continue

                # Rola iniciativa
                init_roll = random.randint(1, 20)
                final_init = init_roll + agi

                await db.execute("""
                    INSERT INTO combatants (name, team, initiative, hp_current, hp_max, dt, original_char_id) 
                    VALUES (?, 'JOGADOR', ?, ?, ?, ?, ?)
                """, (name, final_init, hp, max_hp, player_dt, cid))
                
                added_names.append(f"{name} (Inic {final_init})")
            await db.commit()

        if added_names:
            await interaction.response.send_message(f"✅ Adicionados:\n" + ", ".join(added_names), ephemeral=True)
            await self.update_dashboard(interaction)
        else:
            await interaction.response.send_message("⚠️ Ninguém novo adicionado.", ephemeral=True)

    @app_commands.command(name="add_npc", description="Adiciona Inimigo com DT personalizada.")
    @app_commands.describe(dt="Dificuldade (8=Fácil, 12=Médio, 15=Difícil, 18=M.Difícil, 20=Insano)")
    async def add_npc(self, interaction: discord.Interaction, nome: str, vida: int, iniciativa: int, dt: int):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                INSERT INTO combatants (name, team, initiative, hp_current, hp_max, dt, original_char_id) 
                VALUES (?, 'INIMIGO', ?, ?, ?, ?, NULL)
            """, (nome, iniciativa, vida, vida, dt))
            await db.commit()
        await interaction.response.send_message(f"👾 **{nome}** (DT {dt}) adicionado.", ephemeral=True)
        await self.update_dashboard(interaction)

    # --- AÇÕES E FLUXO ---

    @app_commands.command(name="dano", description="Aplica dano.")
    @app_commands.autocomplete(alvo=combatant_autocomplete)
    async def apply_damage(self, interaction: discord.Interaction, alvo: str, valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id, hp_current, hp_max, original_char_id FROM combatants WHERE name = ?", (alvo,)) as cur:
                if not (row := await cur.fetchone()): return await interaction.response.send_message("❌ Alvo não encontrado.", ephemeral=True)
                cid, curr, max_hp, orig_id = row
            
            new_hp = max(0, curr - valor)
            await db.execute("UPDATE combatants SET hp_current = ? WHERE id = ?", (new_hp, cid))
            if orig_id: await db.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (new_hp, orig_id))
            await db.commit()
        
        await interaction.response.send_message(f"🩸 **{alvo}** tomou {valor} dano.", ephemeral=True)
        await self.update_dashboard(interaction)

    @app_commands.command(name="curar", description="Recupera vida.")
    @app_commands.autocomplete(alvo=combatant_autocomplete)
    async def apply_heal(self, interaction: discord.Interaction, alvo: str, valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id, hp_current, hp_max, original_char_id FROM combatants WHERE name = ?", (alvo,)) as cur:
                if not (row := await cur.fetchone()): return await interaction.response.send_message("❌ Alvo não encontrado.", ephemeral=True)
                cid, curr, max_hp, orig_id = row
            
            new_hp = min(curr + valor, max_hp)
            await db.execute("UPDATE combatants SET hp_current = ? WHERE id = ?", (new_hp, cid))
            if orig_id: await db.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (new_hp, orig_id))
            await db.commit()
        
        await interaction.response.send_message(f"💚 **{alvo}** curou {valor}.", ephemeral=True)
        await self.update_dashboard(interaction)

    @app_commands.command(name="efeito", description="Aplica Efeito.")
    @app_commands.autocomplete(alvo=combatant_autocomplete)
    @app_commands.choices(tipo=[app_commands.Choice(name="Dano por Turno (Sangramento)", value="DOT"), app_commands.Choice(name="Lembrete/Buff (+2 Força)", value="INFO")])
    async def add_effect(self, interaction: discord.Interaction, alvo: str, nome_efeito: str, rodadas: int, tipo: str, valor: int = 0):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id FROM combatants WHERE name = ?", (alvo,)) as cur:
                if not (row := await cur.fetchone()): return await interaction.response.send_message("❌ Alvo não encontrado.", ephemeral=True)
                cid = row[0]
            
            await db.execute("INSERT INTO combat_effects (combatant_id, name, description, duration_rounds, effect_type, value) VALUES (?, ?, '', ?, ?, ?)", 
                             (cid, nome_efeito, rodadas, tipo, valor))
            await db.commit()
        
        await interaction.response.send_message(f"🧪 **{nome_efeito}** em {alvo}.", ephemeral=True)
        await self.update_dashboard(interaction)

    @app_commands.command(name="proximo", description="Avança turno.")
    async def next_turn(self, interaction: discord.Interaction):
        log = []
        async with aiosqlite.connect(DB_NAME) as db:
            # AQUI ESTÁ A MUDANÇA: Ordena APENAS por Iniciativa DESC (Maior primeiro, indiferente do time)
            async with db.execute("SELECT id, name FROM combatants ORDER BY initiative DESC") as cur:
                combatants = await cur.fetchall()
            
            if not combatants: return await interaction.response.send_message("❌ Vazio.", ephemeral=True)

            async with db.execute("SELECT id, round, turn_index FROM combat_state") as cur:
                state = await cur.fetchone()
                _, round_num, turn_idx = state

            next_idx = turn_idx + 1
            
            if next_idx >= len(combatants):
                next_idx = 0
                round_num += 1
                log.append(f"🔔 **RODADA {round_num}**")
                
                async with db.execute("SELECT id, combatant_id, name, duration_rounds, effect_type, value FROM combat_effects") as cur:
                    effects = await cur.fetchall()
                
                for eff in effects:
                    eid, cid, ename, dur, etype, val = eff
                    if etype == 'DOT':
                        async with db.execute("SELECT name, hp_current FROM combatants WHERE id = ?", (cid,)) as ccur:
                            if cdata := await ccur.fetchone():
                                new_hp = max(0, cdata[1] - val)
                                await db.execute("UPDATE combatants SET hp_current = ? WHERE id = ?", (new_hp, cid))
                                log.append(f"🩸 **{cdata[0]}** sofreu {val} ({ename}).")
                    
                    if dur - 1 <= 0:
                        await db.execute("DELETE FROM combat_effects WHERE id = ?", (eid,))
                        log.append(f"✨ {ename} expirou.")
                    else:
                        await db.execute("UPDATE combat_effects SET duration_rounds = ? WHERE id = ?", (dur - 1, eid))

            await db.execute("UPDATE combat_state SET round = ?, turn_index = ?", (round_num, next_idx))
            await db.commit()

        await interaction.response.send_message("\n".join(log) if log else "⏩ Turno avançado.", ephemeral=True)
        await self.update_dashboard(interaction)

    # --- DASHBOARD (COM VISUALIZAÇÃO DE DT) ---
    async def update_dashboard(self, interaction):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT message_id, round, turn_index FROM combat_state") as cur:
                if not (state := await cur.fetchone()): return
                old_msg_id, round_num, turn_idx = state
            
            # Ordenação Pura por Iniciativa
            async with db.execute("SELECT id, name, team, initiative, hp_current, hp_max, dt FROM combatants ORDER BY initiative DESC") as cur:
                combatants = await cur.fetchall()

        """
           pra onde ir?
           ou então, à onde chegar?
           
        """

        if not combatants: return
        embed = discord.Embed(title=f"⚔️ RASTREADOR - RODADA {round_num}", color=0x2b2d31)
        
        desc_txt = ""
        async with aiosqlite.connect(DB_NAME) as db:
            for i, c in enumerate(combatants):
                # c: 0=id, 1=name, 2=team, 3=inic, 4=hp, 5=max, 6=dt
                async with db.execute("SELECT name, duration_rounds, effect_type, value FROM combat_effects WHERE combatant_id = ?", (c[0],)) as cur:
                    effs = await cur.fetchall()
                
                marker = "👉" if i == turn_idx else "▪️"
                
                # Ícones por time
                team_icon = "🛡️" if c[2] == 'JOGADOR' else "👾"
                
                hp_s = f"`HP: {c[4]}/{c[5]}`" if c[4] > 0 else "💀 **MORTO**"
                # Exibe a DT (Defesa)
                dt_s = f"🛡️**DT:{c[6]}**"
                
                eff_s = " ".join([f"| {e[0]}({e[1]})" for e in effs]) if effs else ""
                
                # Monta a linha: 👉 🛡️ Rick (Inic 15) | HP: 10/10 | DT: 12 ...
                line = f"{marker} {team_icon} **{c[1]}** (Inic {c[3]}) | {hp_s} | {dt_s} {eff_s}\n"
                desc_txt += line

        embed.description = desc_txt
        
        channel = interaction.channel
        try:
            old_msg = await channel.fetch_message(old_msg_id)
            await old_msg.delete()
        except: pass

        new_msg = await channel.send(embed=embed)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE combat_state SET message_id = ?", (new_msg.id,))
            await db.commit()

async def setup(bot):
    await bot.add_cog(Combat(bot))