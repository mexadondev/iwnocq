import aiosqlite
import os
from decimal import Decimal
from typing import Optional, List, Dict
from datetime import datetime
import time
import logging
from cryptopay import CryptoPayAPI

class Database:
    def __init__(self, db_path: str = "bunny.casino"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance DECIMAL(10, 2) DEFAULT 0.0,
                    ref_balance DECIMAL(10, 2) DEFAULT 0.0,
                    ref_earnings DECIMAL(10, 2) DEFAULT 0.0,
                    ref_count INTEGER DEFAULT 0,
                    referrer_id INTEGER,
                    seen_instruction INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount DECIMAL(10, 2),
                    type TEXT,
                    game_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount DECIMAL(10, 2),
                    game TEXT,
                    bet_type TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount DECIMAL(10, 2),
                    network TEXT,
                    address TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount DECIMAL(10, 2),
                    game_type TEXT,
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed INTEGER DEFAULT 0,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS win_check_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER,
                    amount DECIMAL(10, 2),
                    used INTEGER DEFAULT 0,
                    check_link TEXT
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invoice_bets (
                    payload TEXT PRIMARY KEY,
                    user_id INTEGER,
                    game_key TEXT,
                    bet_type_key TEXT,
                    amount DECIMAL(10, 2),
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", 
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    
    async def has_seen_instruction(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT seen_instruction FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def mark_instruction_seen(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET seen_instruction = 1 WHERE user_id = ?", (user_id,))
            await db.commit()


    async def create_user(self, user_id: int, username: str, referrer_id: Optional[int] = None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO users 
                (user_id, username, referrer_id) 
                VALUES (?, ?, ?)
                """,
                (user_id, username, referrer_id)
            )
            await db.commit()

    async def update_balance(self, user_id: int, amount: Decimal) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (float(amount), user_id)
            )
            await db.commit()
            return True

    async def update_ref_balance(self, user_id: int, amount: Decimal) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
                (user_id,)
            ) as cursor:
                ref_count = (await cursor.fetchone())[0]

            await db.execute(
                """
                UPDATE users 
                SET ref_balance = ref_balance + ?,
                    ref_earnings = ref_earnings + ?,
                    ref_count = ?
                WHERE user_id = ?
                """,
                (float(amount), float(amount), ref_count, user_id)
            )
            await db.commit()
            return True

    async def get_referrer(self, user_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT referrer_id FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else None

    async def add_to_queue(
        self,
        user_id: int,
        amount: Decimal,
        game: str,
        bet_type: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO queue 
                (user_id, amount, game, bet_type) 
                VALUES (?, ?, ?, ?)
                """,
                (user_id, float(amount), game, bet_type)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_next_bet(self) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM queue 
                WHERE status = 'pending' 
                ORDER BY created_at ASC 
                LIMIT 1
                """
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_bet_processed(self, bet_id: int) -> bool:
        """Отмечает ставку как обработанную"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE bets SET processed = 1, processed_at = datetime('now')
                    WHERE id = ?
                """, (bet_id,))
                await db.commit()
                return True
        except Exception as e:
            logging.error(f"Error marking bet as processed: {e}")
            return False

    async def add_transaction(
        self, 
        user_id: int, 
        amount: Decimal, 
        type: str, 
        game_type: Optional[str] = None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO transactions 
                (user_id, amount, type, game_type) 
                VALUES (?, ?, ?, ?)
                """,
                (user_id, float(amount), type, game_type)
            )
            await db.commit()

    async def get_user_transactions(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
                """,
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_stats(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем все транзакции пользователя типа 'game'
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total_games,
                    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN amount <= 0 THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_won,
                    SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_lost,
                    SUM(ABS(amount)) as turnover
                FROM transactions 
                WHERE user_id = ? AND type = 'game'
            """, (user_id,))
            row = await cursor.fetchone()
            
            total_games = row[0] or 0
            wins = row[1] or 0
            losses = row[2] or 0
            total_won = float(row[3] or 0)
            total_lost = float(row[4] or 0)
            turnover = float(row[5] or 0)
            
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            return {
                'total_games': total_games,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'turnover': turnover,
                'total_won': total_won,
                'total_lost': total_lost
            }

    async def create_withdrawal(
        self,
        user_id: int,
        amount: float,
        network: str,
        address: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO withdrawals 
                (user_id, amount, network, address) 
                VALUES (?, ?, ?, ?)
                """,
                (user_id, amount, network, address)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_pending_withdrawals(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT w.*, u.username 
                FROM withdrawals w
                JOIN users u ON w.user_id = u.user_id
                WHERE w.status = 'pending'
                ORDER BY w.created_at ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_withdrawal_processed(self, withdrawal_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE withdrawals 
                SET status = 'processed',
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (withdrawal_id,)
            )
            await db.commit()

    async def cancel_withdrawal(self, withdrawal_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            # First get the withdrawal details
            async with db.execute(
                "SELECT user_id, amount FROM withdrawals WHERE id = ?",
                (withdrawal_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_id, amount = row
                    # Return the funds to the user's balance
                    await db.execute(
                        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                        (amount, user_id)
                    )
                    # Mark withdrawal as cancelled
                    await db.execute(
                        """
                        UPDATE withdrawals 
                        SET status = 'cancelled',
                            processed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (withdrawal_id,)
                    )
                    await db.commit()

    async def get_user_withdrawals(self, user_id: int, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM withdrawals 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_admin_stats(self) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            stats = {}
            
            # Get total users and registrations
            async with db.execute(
                """
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN date(created_at) = date('now') THEN 1 ELSE 0 END) as today_users,
                    SUM(CASE WHEN date(created_at) >= date('now', '-7 days') THEN 1 ELSE 0 END) as week_users
                FROM users
                """
            ) as cursor:
                user_stats = dict(await cursor.fetchone())
                stats.update(user_stats)

            # Get game statistics for today
            async with db.execute(
                """
                SELECT 
                    COUNT(DISTINCT id) as today_games,
                    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as today_wins,
                    SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) as today_losses,
                    SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END) as today_draws,
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as today_spent,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as today_earned,
                    COALESCE(SUM(ABS(amount)), 0) as today_turnover
                FROM transactions 
                WHERE type = 'game' 
                AND date(created_at) = date('now')
                AND game_type NOT LIKE '%_cashback'
                """
            ) as cursor:
                today_stats = dict(await cursor.fetchone())
                stats.update(today_stats)

            # Get game statistics for week
            async with db.execute(
                """
                SELECT 
                    COUNT(DISTINCT id) as week_games,
                    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as week_wins,
                    SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) as week_losses,
                    SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END) as week_draws,
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as week_spent,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as week_earned,
                    COALESCE(SUM(ABS(amount)), 0) as week_turnover
                FROM transactions 
                WHERE type = 'game' 
                AND date(created_at) >= date('now', '-7 days')
                AND game_type NOT LIKE '%_cashback'
                """
            ) as cursor:
                week_stats = dict(await cursor.fetchone())
                stats.update(week_stats)

            # Get total statistics
            async with db.execute(
                """
                SELECT 
                    COUNT(DISTINCT id) as total_bets,
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_spent,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_earned,
                    COALESCE(SUM(ABS(amount)), 0) as total_turnover
                FROM transactions 
                WHERE type = 'game'
                AND game_type NOT LIKE '%_cashback'
                """
            ) as cursor:
                total_stats = dict(await cursor.fetchone())
                stats.update(total_stats)

            # Get withdrawal statistics
            async with db.execute(
                """
                SELECT 
                    COALESCE(SUM(amount), 0) as total_withdrawals,
                    COALESCE(SUM(CASE WHEN date(created_at) = date('now') THEN amount ELSE 0 END), 0) as today_withdrawals,
                    COALESCE(SUM(CASE WHEN date(created_at) >= date('now', '-7 days') THEN amount ELSE 0 END), 0) as week_withdrawals
                FROM withdrawals 
                WHERE status = 'processed'
                """
            ) as cursor:
                withdrawal_stats = dict(await cursor.fetchone())
                stats.update(withdrawal_stats)

            # Debug: Get raw transactions data
            async with db.execute(
                """
                SELECT * FROM transactions 
                WHERE type = 'game' 
                ORDER BY created_at DESC 
                LIMIT 5
                """
            ) as cursor:
                recent_transactions = await cursor.fetchall()
                if recent_transactions:
                    logging.info("Recent transactions found:")
                    for tx in recent_transactions:
                        logging.info(f"Transaction: {dict(tx)}")
                else:
                    logging.info("No recent transactions found")

            return stats 

    async def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT u.*, 
                       (SELECT username FROM users WHERE user_id = u.referrer_id) as referrer_username
                FROM users u
                ORDER BY u.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_user(self, user_id: int, updates: Dict) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            # Build the update query dynamically based on provided fields
            fields = []
            values = []
            for key, value in updates.items():
                if key in ['balance', 'ref_balance', 'ref_earnings', 'username', 'referrer_id', 'ref_count']:
                    fields.append(f"{key} = ?")
                    values.append(value)
            
            if not fields:
                return False
                
            query = f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?"
            values.append(user_id)
            
            await db.execute(query, values)
            await db.commit()
            return True

    async def delete_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            # First delete related records
            await db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM withdrawals WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
            
            # Then delete the user
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()
            return True

    async def search_users(self, query: str) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT u.*, 
                       (SELECT username FROM users WHERE user_id = u.referrer_id) as referrer_username
                FROM users u
                WHERE u.username LIKE ? OR u.user_id LIKE ?
                ORDER BY u.created_at DESC
                LIMIT 50
                """,
                (f"%{query}%", f"%{query}%")
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def add_bet(self, user_id: int, amount: float, game_type: str, message_id: int) -> int:
        """Добавляет ставку в очередь и возвращает её ID"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO bets (user_id, amount, game_type, message_id, created_at, processed)
                VALUES (?, ?, ?, ?, datetime('now'), 0)
            """, (user_id, amount, game_type, message_id))
            await db.commit()
            return cursor.lastrowid 

    async def add_invoice_bet(self, payload: str, user_id: int, game_key: str, bet_type_key: str, amount: Decimal) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO invoice_bets 
                (payload, user_id, game_key, bet_type_key, amount) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload, user_id, game_key, bet_type_key, float(amount))
            )
            await db.commit()

    async def get_invoice_bet(self, payload: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM invoice_bets WHERE payload = ?", 
                (payload,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_invoice_bet_paid(self, payload: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE invoice_bets SET status = 'paid' WHERE payload = ?",
                (payload,)
            )
            await db.commit()

    async def get_current_balance(self) -> float:
        """Возвращает текущий баланс казны (из CryptoPay API)"""
        try:
            crypto_pay = CryptoPayAPI(os.getenv('CRYPTO_PAY_TOKEN'))
            balance_data = await crypto_pay.get_balance()
            
            balances = balance_data.get('result', [])
            usdt_balance = 0
            
            # Находим USDT баланс
            for balance in balances:
                currency = balance.get('currency_code', '')
                available = balance.get('available', '0')
                
                if currency and currency.upper() == 'USDT':
                    usdt_balance = float(available)
                    break
            
            return usdt_balance
        except Exception as e:
            logging.error(f"Error getting current balance: {e}")
            return 0.0 

    async def save_win_check_token(self, token: str, user_id: int, amount: float, check_link: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO win_check_tokens (token, user_id, amount, used, check_link) VALUES (?, ?, ?, 0, ?)",
                (token, user_id, amount, check_link)
            )
            await db.commit()

    async def get_win_check_token(self, token: str):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM win_check_tokens WHERE token = ? AND used = 0",
                (token,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_win_check_token_used(self, token: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE win_check_tokens SET used = 1 WHERE token = ?",
                (token,)
            )
            await db.commit() 