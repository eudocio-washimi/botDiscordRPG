import discord
from discord import app_commands
from discord.ext import commands
import random
import re
import aiosqlite
from database import DB_NAME

# --- CONFIGURAÇÃO DAS CLASSES ---
CLASSES_INFO = {
    "O Atleta": {
        "bonus": {"FOR": 1},
        "traits": [("Resistência Física", "Ignora 1 de dano corpo a corpo.", "CLASSE"), ("Mobilidade Aprimorada", "Consegue escalar/correr melhor.", "CLASSE")]
    },
    "O Faz-Tudo": {
        "bonus": {"INT": 1},
        "traits": [("Improvisação", "Cria equipamentos improvisados.", "CLASSE"), ("Equipamento Aleatório", "Inicia com item extra.", "CLASSE")]
    },
    "O Ladrão": {
        "bonus": {"AGI": 2},
        "traits": [("Ataque Furtivo", "+1 dano furtivo.", "CLASSE"), ("Passos Leves", "Furtividade aprimorada.", "CLASSE"), ("Desastrado", "Falhas críticas geram barulho.", "FRAQUEZA")]
    },
    "O Líder": {
        "bonus": {"CAR": 2},
        "traits": [("Inspirar Confiança", "Reduz estresse do grupo (1x/sessão).", "CLASSE"), ("Solução Inusitada", "Resolve situações de forma criativa.", "CLASSE")]
    },
    "O Médico Improvisado": {
        "bonus": {"INT": 1},
        "traits": [("Primeiros Socorros", "Cura sem teste com suprimentos.", "CLASSE")]
    },
    "O Buscador": {
        "bonus": {"AGI": 1},
        "traits": [("Senso de Direção", "Encontra rotas de fuga.", "CLASSE"), ("Olhos de Águia", "Encontra itens úteis.", "CLASSE")]
    },
    "O Atirador Inseguro": {
        "bonus": {"INT": 1},
        "traits": [("Mira Tensa", "+1 dano com armas de fogo.", "CLASSE"), ("Dedo Nervoso", "Falhas críticas atrapalham o grupo.", "FRAQUEZA")]
    },
    "O Malandro": {
        "bonus": {"CAR": 1},
        "traits": [("Lábia", "+2 em blefes.", "CLASSE"), ("Ludibriar", "Manipula NPCs.", "CLASSE")]
    }
}

class Player(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        content = message.content.strip().replace(" ", "")
        match = re.search(r'^(\d*)d(\d+)([+-][\w\d]+)?$', content, re.IGNORECASE)

        if match:
            qty_str, faces_str, modifier_str = match.groups()
            qtd = int(qty_str) if qty_str else 1
            faces = int(faces_str)
            if qtd > 50 or faces > 1000: return
            rolls = [random.randint(1, faces) for _ in range(qtd)]
            raw_total = sum(rolls)
            mod_val = 0
            if modifier_str:
                operator = modifier_str[0]
                value_part = modifier_str[1:].upper()
                if value_part.isdigit():
                    val = int(value_part)
                else:
                    val = await self.get_attribute_value(message.channel.id, value_part)
                mod_val = val if operator == '+' else -val
            final_total = raw_total + mod_val
            rolls_display = f"[{', '.join(map(str, rolls))}]"
            await message.channel.send(f"{message.author.mention} ` {final_total} ` ⟵ {rolls_display} {content.lower()}")

    async def get_attribute_value(self, channel_id, attr_name):
        mapping = {'FOR': 5, 'AGI': 6, 'VIG': 7, 'INT': 8, 'CAR': 9}
        idx = mapping.get(attr_name, -1)
        if idx == -1: return 0
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT * FROM characters WHERE channel_id = ?", (channel_id,)) as cursor:
                char = await cursor.fetchone()
                if char: return char[idx]
        return 0

    @app_commands.command(name="criar", description="Cria ficha. (Use TAB para alternar campos)")
    @app_commands.describe(
        nome="Nome do Personagem", 
        classe="Classe", 
        forca="Pontos em FOR", 
        agi="Pontos em AGI", 
        vig="Pontos em VIG", 
        inte="Pontos em INT", 
        car="Pontos em CAR"
    )
    # AQUI ESTÁ A MUDANÇA: 'rename' força o nome no Discord (mas obriga ser minúsculo)
    @app_commands.rename(forca="for", agi="agi", vig="vig", inte="int", car="car")
    @app_commands.choices(classe=[app_commands.Choice(name=k, value=k) for k in CLASSES_INFO.keys()])
    async def create_char(self, interaction: discord.Interaction, nome: str, classe: app_commands.Choice[str], forca: int, agi: int, vig: int, inte: int, car: int):
        
        # Validação
        if any(a > 4 for a in [forca, agi, vig, inte, car]):
            await interaction.response.send_message("⚠️ Máximo 4 pontos base por atributo.", ephemeral=True)
            return
        if sum([forca, agi, vig, inte, car]) > 12:
            await interaction.response.send_message(f"⚠️ Usou {sum([forca, agi, vig, inte, car])} pontos. Limite é 12.", ephemeral=True)
            return

        class_name = classe.value
        class_data = CLASSES_INFO.get(class_name)
        
        final_for = forca + class_data["bonus"].get("FOR", 0)
        final_agi = agi + class_data["bonus"].get("AGI", 0)
        final_vig = vig + class_data["bonus"].get("VIG", 0)
        final_int = inte + class_data["bonus"].get("INT", 0)
        final_car = car + class_data["bonus"].get("CAR", 0)

        guild = interaction.guild
        mestre_role = discord.utils.get(guild.roles, name="Mestre")
        clean_name = re.sub(r'[^a-z0-9\-_]', '', nome.lower().replace(' ', '-'))
        channel_name = f"ficha-{clean_name}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if mestre_role: overwrites[mestre_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        category = discord.utils.get(guild.categories, name="ÁREA DO JOGADOR")
        if not category: category = await guild.create_category("ÁREA DO JOGADOR")

        try:
            new_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao criar canal: {e}", ephemeral=True)
            return

        hp_max = 10 + final_vig
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                INSERT INTO characters (user_id, channel_id, name, classe, forca, agilidade, vigor, inteligencia, carisma, hp_current, hp_bonus, stress_current)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (interaction.user.id, new_channel.id, nome, class_name, final_for, final_agi, final_vig, final_int, final_car, hp_max, 0, 0))
            
            for t_name, t_desc, t_type in class_data["traits"]:
                await db.execute("INSERT INTO traits (channel_id, name, description, type) VALUES (?, ?, ?, ?)", (new_channel.id, t_name, t_desc, t_type))
            await db.commit()

        await interaction.response.send_message(f"✅ Criado: {new_channel.mention}", ephemeral=True)
        embed = await self.get_sheet_embed(new_channel.id)
        msg = await new_channel.send(content=f"{interaction.user.mention} Ficha criada.", embed=embed)
        await msg.pin()

    @app_commands.command(name="ficha", description="Ver ficha.")
    async def view_sheet(self, interaction: discord.Interaction):
        embed = await self.get_sheet_embed(interaction.channel_id)
        if embed: await interaction.response.send_message(embed=embed)
        else: await interaction.response.send_message("❌ Use no canal do personagem.", ephemeral=True)

    @app_commands.command(name="bonus_hp", description="Bônus de HP Máximo.")
    async def set_hp_bonus(self, interaction: discord.Interaction, valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id FROM characters WHERE channel_id = ?", (interaction.channel_id,)) as cursor:
                if not await cursor.fetchone(): return await interaction.response.send_message("❌ Use no canal do personagem.", ephemeral=True)
            await db.execute("UPDATE characters SET hp_bonus = ? WHERE channel_id = ?", (valor, interaction.channel_id))
            await db.commit()
        await interaction.response.send_message(f"✨ Bônus HP: {valor:+d}")
        embed = await self.get_sheet_embed(interaction.channel_id)
        if embed: await interaction.channel.send(embed=embed)

    @app_commands.command(name="hp", description="Alterar HP Atual.")
    async def modify_hp(self, interaction: discord.Interaction, valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT vigor, hp_current, hp_bonus FROM characters WHERE channel_id = ?", (interaction.channel_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return await interaction.response.send_message("❌ Erro.", ephemeral=True)
                vig, curr, bonus = row
                max_hp = 10 + vig + bonus
            new_hp = max(0, min(curr + valor, max_hp))
            await db.execute("UPDATE characters SET hp_current = ? WHERE channel_id = ?", (new_hp, interaction.channel_id))
            await db.commit()
            await interaction.response.send_message(f"🩸 {abs(valor)} HP. ({new_hp}/{max_hp})")

    @app_commands.command(name="estresse", description="Alterar Estresse.")
    async def modify_stress(self, interaction: discord.Interaction, valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT stress_current FROM characters WHERE channel_id = ?", (interaction.channel_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return await interaction.response.send_message("❌ Erro.", ephemeral=True)
                curr = row[0]
            new = max(0, min(curr + valor, 10))
            await db.execute("UPDATE characters SET stress_current = ? WHERE channel_id = ?", (new, interaction.channel_id))
            await db.commit()
            await interaction.response.send_message(f"🤯 Estresse: {new}/10")

    @app_commands.command(name="editar", description="Edita atributos.")
    @app_commands.choices(atributo=[app_commands.Choice(name=k, value=v) for k,v in {"Força":"forca", "Agilidade":"agilidade", "Vigor":"vigor", "Int":"inteligencia", "Carisma":"carisma"}.items()])
    async def edit_attr(self, interaction: discord.Interaction, atributo: app_commands.Choice[str], valor: int):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id FROM characters WHERE channel_id = ?", (interaction.channel_id,)) as cursor:
                if not await cursor.fetchone(): return await interaction.response.send_message("❌ Erro.", ephemeral=True)
            await db.execute(f"UPDATE characters SET {atributo.value} = ? WHERE channel_id = ?", (valor, interaction.channel_id))
            await db.commit()
        await interaction.response.send_message(f"✏️ {atributo.name} atualizado.")
        embed = await self.get_sheet_embed(interaction.channel_id)
        if embed: await interaction.channel.send(embed=embed)

    @app_commands.command(name="habilidade", description="Adiciona uma habilidade.")
    async def add_skill_cmd(self, interaction: discord.Interaction, nome: str, descricao: str):
        await self.add_trait_logic(interaction, nome, descricao, "HABILIDADE")

    @app_commands.command(name="fraqueza", description="Adiciona uma fraqueza.")
    async def add_weak_cmd(self, interaction: discord.Interaction, nome: str, descricao: str):
        await self.add_trait_logic(interaction, nome, descricao, "FRAQUEZA")

    @app_commands.command(name="remover_trait", description="Remove habilidade ou fraqueza.")
    async def remove_trait_cmd(self, interaction: discord.Interaction, nome: str):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM traits WHERE channel_id = ? AND name = ?", (interaction.channel_id, nome))
            await db.commit()
        await interaction.response.send_message(f"🗑️ Traço **{nome}** removido.")
        embed = await self.get_sheet_embed(interaction.channel_id)
        if embed: await interaction.channel.send(embed=embed)

    async def add_trait_logic(self, interaction, name, desc, type_t):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id FROM characters WHERE channel_id = ?", (interaction.channel_id,)) as cursor:
                if not await cursor.fetchone(): return await interaction.response.send_message("❌ Canal sem ficha.", ephemeral=True)
            await db.execute("INSERT INTO traits (channel_id, name, description, type) VALUES (?, ?, ?, ?)", (interaction.channel_id, name, desc, type_t))
            await db.commit()
        await interaction.response.send_message(f"✨ **{type_t.capitalize()}** adicionada: {name}")
        embed = await self.get_sheet_embed(interaction.channel_id)
        await interaction.channel.send(embed=embed)

    async def get_sheet_embed(self, channel_id):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT * FROM characters WHERE channel_id = ?", (channel_id,)) as cursor:
                char = await cursor.fetchone()
            if not char: return None
            async with db.execute("SELECT name, description, type FROM traits WHERE channel_id = ?", (channel_id,)) as cursor:
                traits = await cursor.fetchall()
        
        c_name, c_class = char[3], char[4]
        c_stats = {'FOR': char[5], 'AGI': char[6], 'VIG': char[7], 'INT': char[8], 'CAR': char[9]}
        c_hp, c_bonus, c_stress = char[10], char[11], char[12]
        hp_max = 10 + c_stats['VIG'] + c_bonus

        embed = discord.Embed(title=f"🧟 {c_name}", color=0x2b2d31)
        embed.add_field(name="Classe", value=c_class, inline=True)
        embed.add_field(name="Vitalidade", value=f"❤️ HP: {c_hp}/{hp_max}\n🤯 Estresse: {c_stress}/10", inline=True)
        embed.add_field(name="Atributos", value=f"```FOR: {c_stats['FOR']} | INT: {c_stats['INT']}\nAGI: {c_stats['AGI']} | CAR: {c_stats['CAR']}\nVIG: {c_stats['VIG']}```", inline=False)
        
        # Filtros de Habilidades
        class_skills = [f"🛡️ **{t[0]}**: {t[1]}" for t in traits if t[2] == 'CLASSE']
        other_skills = [f"⚡ **{t[0]}**: {t[1]}" for t in traits if t[2] == 'HABILIDADE']
        weaks = [f"🔻 **{t[0]}**: {t[1]}" for t in traits if t[2] == 'FRAQUEZA']
        
        if class_skills: embed.add_field(name="Habilidades de Classe", value="\n".join(class_skills), inline=False)
        if other_skills: embed.add_field(name="Habilidades Adquiridas", value="\n".join(other_skills), inline=False)
        if weaks: embed.add_field(name="Fraquezas", value="\n".join(weaks), inline=False)
        return embed

async def setup(bot):
    await bot.add_cog(Player(bot))