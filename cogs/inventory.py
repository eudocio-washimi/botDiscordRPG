import discord
from discord.ext import commands
import aiosqlite
from database import DB_NAME
# Tentamos importar de utils, mas se falhar, definimos um padrão para não quebrar
try:
    from utils import calculate_load, BACKPACKS
except ImportError:
    BACKPACKS = {"Mochila simples": 5, "Mochila grande": 8}
    async def calculate_load(user_id): return 0, 10, False

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='item', invoke_without_command=True)
    async def item_group(self, ctx):
        await ctx.send("Use: `/item adicionar`, `/item remover`, `/item listar`")

    @item_group.command(name='adicionar')
    async def add_item(self, ctx, nome: str, slots: int = 1):
        """Adiciona item: /item adicionar "Nome" Slots"""
        async with aiosqlite.connect(DB_NAME) as db:
            # Verifica se tem ficha no canal
            async with db.execute("SELECT id FROM characters WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                if not await cursor.fetchone():
                    await ctx.reply("❌ Use este comando no canal do personagem.")
                    return

            await db.execute("INSERT INTO inventory (channel_id, item_name, slots) VALUES (?, ?, ?)", 
                             (ctx.channel.id, nome, slots))
            await db.commit()
        
        await self.check_load(ctx)

    @item_group.command(name='remover')
    async def remove_item(self, ctx, nome: str):
        """Remove item pelo nome."""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM inventory WHERE id IN (SELECT id FROM inventory WHERE channel_id = ? AND item_name = ? LIMIT 1)", (ctx.channel.id, nome))
            await db.commit()
        await ctx.send(f"🗑️ Item **{nome}** removido.")

    @item_group.command(name='listar')
    async def list_items(self, ctx):
        """Lista inventário."""
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT item_name, slots FROM inventory WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                items = await cursor.fetchall()

        if not items:
            await ctx.send("🎒 Sua mochila está vazia.")
            return

        lista = "\n".join([f"- **{i[0]}** ({i[1]} slots)" for i in items])
        
        cur, max_l, over = await self.calculate_load_internal(ctx.channel.id)
        
        embed = discord.Embed(title="🎒 Inventário", description=lista, color=0xe67e22)
        embed.set_footer(text=f"Carga: {cur}/{max_l} {'⚠️ SOBRECARGA' if over else ''}")
        await ctx.send(embed=embed)

    @commands.group(name='mochila', invoke_without_command=True)
    async def backpack_group(self, ctx):
        await ctx.send("Use: `/mochila equipar` ou `/mochila remover`")

    @backpack_group.command(name='equipar')
    async def equip_backpack(self, ctx, *, tipo: str):
        if tipo not in BACKPACKS:
            await ctx.send(f"❌ Tipo inválido. Opções: {', '.join(BACKPACKS.keys())}")
            return
            
        async with aiosqlite.connect(DB_NAME) as db:
            # Verifica ficha
            async with db.execute("SELECT id FROM characters WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                if not await cursor.fetchone():
                    await ctx.send("❌ Sem ficha neste canal.")
                    return
            
            await db.execute("UPDATE characters SET backpack_type = ? WHERE channel_id = ?", (tipo, ctx.channel.id))
            await db.commit()
        await ctx.send(f"🎒 Você equipou: **{tipo}**")

    async def check_load(self, ctx):
        cur, max_l, over = await self.calculate_load_internal(ctx.channel.id)
        msg = f"Item registrado. Carga atual: {cur}/{max_l}."
        if over: msg += "\n⚠️ **VOCÊ ESTÁ SOBRECARREGADO!** (-2 AGI, Sem correr)"
        await ctx.send(msg)

    # Função interna para calcular carga (independente de utils.py)
    async def calculate_load_internal(self, channel_id):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT forca, backpack_type FROM characters WHERE channel_id = ?", (channel_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return 0, 0, False
                forca, pack_type = row
            
            async with db.execute("SELECT SUM(slots) FROM inventory WHERE channel_id = ?", (channel_id,)) as cursor:
                total_slots = (await cursor.fetchone())[0] or 0

        pack_bonus = BACKPACKS.get(pack_type, 0)
        max_load = 3 + forca + pack_bonus
        overloaded = total_slots > max_load
        return total_slots, max_load, overloaded

async def setup(bot):
    await bot.add_cog(Inventory(bot))