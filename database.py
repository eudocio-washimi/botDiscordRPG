import aiosqlite

DB_NAME = "zombie_rpg.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # --- TABELAS DE PERSONAGEM ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id INTEGER UNIQUE,
                name TEXT,
                classe TEXT,
                forca INTEGER,
                agilidade INTEGER,
                vigor INTEGER,
                inteligencia INTEGER,
                carisma INTEGER,
                hp_current INTEGER,
                hp_bonus INTEGER DEFAULT 0,
                stress_current INTEGER,
                stress_perm INTEGER DEFAULT 0,
                backpack_type TEXT DEFAULT 'Nenhuma',
                notes TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                item_name TEXT,
                slots INTEGER,
                FOREIGN KEY(channel_id) REFERENCES characters(channel_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS traits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                name TEXT,
                description TEXT,
                type TEXT,
                FOREIGN KEY(channel_id) REFERENCES characters(channel_id)
            )
        """)

        # --- TABELAS DE COMBATE (ATUALIZADAS) ---
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS combat_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER, 
                message_id INTEGER, 
                round INTEGER DEFAULT 1,
                turn_index INTEGER DEFAULT 0
            )
        """)

        # ADICIONADO: Coluna 'dt' (Dificuldade do Teste / Defesa)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS combatants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                team TEXT,
                initiative INTEGER,
                hp_current INTEGER,
                hp_max INTEGER,
                dt INTEGER DEFAULT 10,  -- Nova coluna para a Defesa
                original_char_id INTEGER,
                is_active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS combat_effects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combatant_id INTEGER,
                name TEXT,
                description TEXT,
                duration_rounds INTEGER,
                effect_type TEXT,
                value INTEGER,
                FOREIGN KEY(combatant_id) REFERENCES combatants(id) ON DELETE CASCADE
            )
        """)

        await db.commit()