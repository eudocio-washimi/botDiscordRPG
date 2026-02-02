import discord
import os
import asyncio
import traceback # Essencial para ver o detalhe do erro
from discord.ext import commands
from database import init_db
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuração de Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- SISTEMA DE LOG DE ERROS (O Segredo) ---
# Isto captura erros dentro dos comandos / (Slash) e mostra no terminal
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    print(f"\n❌ ERRO CRÍTICO NO COMANDO '/{interaction.command.name}':")
    # Imprime o erro completo no terminal
    traceback.print_exception(type(error), error, error.__traceback__)
    
    # Tenta avisar o usuário no Discord se possível
    if not interaction.response.is_done():
        await interaction.response.send_message(f"🔥 Erro interno no código (veja o terminal): {error}", ephemeral=True)

@bot.event
async def on_ready():
    print('\n' + '='*30)
    print(f'✅ LOGIN REALIZADO: {bot.user}')
    print(f'🆔 ID do Bot: {bot.user.id}')
    
    try:
        await init_db()
        print('📂 Banco de Dados: Conectado e Tabelas Criadas.')
    except Exception as e:
        print(f'❌ ERRO NO BANCO DE DADOS: {e}')

    print('🔄 Sincronizando comandos com o Discord...')
    try:
        synced = await bot.tree.sync()
        print(f'✨ Sincronização Concluída: {len(synced)} comandos Slash ativos.')
    except Exception as e:
        print(f'❌ ERRO AO SINCRONIZAR: {e}')
    print('='*30 + '\n')

async def load_extensions():
    # Lista dos seus módulos
    extensions = [
        'cogs.player',
        'cogs.inventory',
        'cogs.master',
        'cogs.combat'  # O novo módulo de batalha
    ]
    
    print("--- CARREGANDO MÓDULOS ---")
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f'🟢 Sucesso: {ext}')
        except Exception as e:
            print(f'🔴 FALHA AO CARREGAR {ext}:')
            # Mostra o erro exato do porquê o módulo falhou
            traceback.print_exc() 
    print("--------------------------")

async def main():
    if not TOKEN:
        print("❌ ERRO: O Token não está no arquivo .env!")
        return

    async with bot:
        await load_extensions()
        try:
            await bot.start(TOKEN)
        except Exception as e:
            print(f"❌ Erro ao iniciar o bot: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot desligado pelo usuário.")