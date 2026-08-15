"""
طبقة قاعدة البيانات (SQLite) لتخزين سجل المحادثات بشكل دائم
------------------------------------------------------------
تُنشئ ملف قاعدة بيانات محلي (bot_data.db) يحفظ كل رسالة لكل مستخدم،
بحيث ما تنمسح المحادثة عند إعادة تشغيل البوت.
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "bot_data.db"


def init_db() -> None:
    """إنشاء الجدول إذا ما كان موجود"""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_id ON messages(chat_id)"
        )
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def add_message(chat_id: int, role: str, content: str) -> None:
    """إضافة رسالة جديدة لسجل المستخدم"""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        conn.commit()


def get_history(chat_id: int, limit: int = 20) -> list[dict]:
    """جلب آخر (limit) رسالة لمستخدم معين، مرتبة من الأقدم للأحدث"""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT role, content FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        )
        rows = cursor.fetchall()
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def clear_history(chat_id: int) -> None:
    """مسح سجل محادثة مستخدم معين"""
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
