from database import get_db

# Regra do sistema: Carga Base = 3 + FOR
BASE_CAPACITY = 3

BACKPACKS = {
    "Nenhuma": 0,
    "Mochila simples": 5,
    "Mochila grande": 8
}

async def calculate_load(user_id):
    """Retorna (peso_atual, peso_maximo, esta_sobrecarregado)"""
    async with await get_db() as db:
        async with db.execute("SELECT forca, backpack_type FROM characters WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return 0, 0, False
            
            forca, backpack_type = row
            # Nova fórmula: 3 + FOR + Mochila
            max_load = BASE_CAPACITY + forca + BACKPACKS.get(backpack_type, 0)

        async with db.execute("SELECT SUM(slots) FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            current_load = result[0] if result[0] else 0

    return current_load, max_load, (current_load > max_load)