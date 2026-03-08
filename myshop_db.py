#!/usr/bin/env python3
"""
あるけみすと myshop 価格履歴 DB
SQLite で価格の推移を記録
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "myshop_prices.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sampled_at TEXT NOT NULL,
                category TEXT,
                item_name TEXT NOT NULL,
                enhance INTEGER NOT NULL DEFAULT 0,
                price INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_price_log_item
            ON price_log(category, item_name, enhance, sampled_at)
        """)


def insert_prices(items: list[dict]) -> int:
    """価格リストを1スナップショットとして挿入。戻り値: 挿入件数"""
    now = datetime.now().isoformat()
    rows = []
    for i in items:
        rows.append((
            now,
            i.get("category") or "",
            i["item_name"],
            i.get("enhance", 0),
            i["price"],
        ))
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO price_log (sampled_at, category, item_name, enhance, price) VALUES (?,?,?,?,?)",
            rows,
        )
    return len(rows)


def get_price_history(
    category: str | None = None,
    item_name: str | None = None,
    enhance: int | None = None,
    limit_days: int | None = 30,
) -> list[dict]:
    """
    価格履歴を取得。
    category, item_name, enhance で絞り込み可能。
    """
    conditions = []
    params: list = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if item_name:
        conditions.append("item_name = ?")
        params.append(item_name)
    if enhance is not None:
        conditions.append("enhance = ?")
        params.append(enhance)
    if limit_days:
        conditions.append("date(sampled_at) >= date('now', ?)")
        params.append(f"-{limit_days} days")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
        SELECT sampled_at, category, item_name, enhance, price
        FROM price_log
        WHERE {where}
        ORDER BY sampled_at DESC, price ASC
    """
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def get_price_summary(
    category: str | None = None,
    limit_days: int = 30,
) -> list[dict]:
    """
    アイテム別の価格サマリ（直近の min/max/avg）
    """
    params: list = [f"-{limit_days} days"]
    where_cat = ""
    if category:
        where_cat = "AND category = ?"
        params.append(category)
    sql = f"""
        SELECT
            category,
            item_name,
            enhance,
            MIN(price) as min_price,
            MAX(price) as max_price,
            ROUND(AVG(price), 0) as avg_price,
            COUNT(*) as sample_count,
            MAX(sampled_at) as last_seen
        FROM price_log
        WHERE date(sampled_at) >= date('now', ?) {where_cat}
        GROUP BY category, item_name, enhance
        ORDER BY category, item_name, enhance
    """
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def get_snapshots(limit: int = 100) -> list[str]:
    """記録されたスナップショット日時の一覧（最新順）"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT DISTINCT sampled_at FROM price_log ORDER BY sampled_at DESC LIMIT ?",
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]
