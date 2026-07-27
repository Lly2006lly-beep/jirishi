# -*- coding: utf-8 -*-
"""
今日事 Web - 数据库模型
支持 SQLite（本地开发）和 PostgreSQL（Render 线上）。
自动根据 DATABASE_URL 环境变量切换数据库类型。
"""

import os
import sqlite3
from datetime import datetime, timedelta

# 尝试导入 PostgreSQL 驱动
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

_db_type = None  # 'sqlite' 或 'postgresql'


def get_db():
    """获取数据库连接，自动根据 DATABASE_URL 选择 SQLite 或 PostgreSQL"""
    global _db_type
    db_url = os.environ.get('DATABASE_URL')

    if db_url and HAS_PSYCOPG2:
        _db_type = 'postgresql'
        conn = psycopg2.connect(db_url)
        # psycopg2 返回普通元组，我们在查询时手动用列名
        return conn
    else:
        _db_type = 'sqlite'
        conn = sqlite3.connect('tasks.db')
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _execute(cursor, sql, params=None):
    """执行 SQL，自动转换占位符（SQLite 用 ?，PostgreSQL 用 %s）"""
    if _db_type == 'postgresql':
        sql = sql.replace('?', '%s')
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)


def _fetchone(cursor, sql, params=None):
    """查询单行，返回 dict"""
    _execute(cursor, sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    if _db_type == 'postgresql':
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    else:
        return dict(row)


def _fetchall(cursor, sql, params=None):
    """查询多行，返回 list[dict]"""
    _execute(cursor, sql, params)
    rows = cursor.fetchall()
    if _db_type == 'postgresql':
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    else:
        return [dict(row) for row in rows]


def _now():
    """返回当前日期时间字符串"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _today():
    """返回当前日期字符串"""
    return datetime.now().strftime('%Y-%m-%d')


# ==================== 初始化数据库 ====================

def init_db():
    """初始化数据库：创建所有表"""
    conn = get_db()
    cursor = conn.cursor()

    if _db_type == 'postgresql':
        # PostgreSQL 建表语句
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('todo', 'done')),
                created_date TEXT NOT NULL,
                completed_time TEXT,
                due_date TEXT,
                priority INTEGER DEFAULT 2 CHECK(priority IN (1, 2, 3)),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                remind_days INTEGER,
                last_reminded_date TEXT,
                notes TEXT,
                tags TEXT,
                category TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_reminder (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                reminded INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(user_id, name)
            )
        """)
    else:
        # SQLite 建表语句
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('todo', 'done')),
                created_date TEXT NOT NULL,
                completed_time TEXT,
                due_date TEXT,
                priority INTEGER DEFAULT 2 CHECK(priority IN (1, 2, 3)),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                remind_days INTEGER,
                last_reminded_date TEXT,
                notes TEXT,
                tags TEXT,
                category TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_reminder (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                reminded INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(user_id, name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

    conn.commit()
    conn.close()


# ==================== 用户管理 ====================

def create_user(username, password_hash):
    """创建新用户"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        now = _now()
        _execute(cursor,
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username.strip(), password_hash, now)
        )
        if _db_type == 'postgresql':
            _execute(cursor, "SELECT LASTVAL()")
            user_id = cursor.fetchone()[0]
        else:
            user_id = cursor.lastrowid
        conn.commit()

        # 默认分类
        for default_cat in ['工作', '学习', '生活']:
            _execute(cursor,
                "INSERT INTO categories (user_id, name) SELECT ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE user_id = ? AND name = ?)",
                (user_id, default_cat, user_id, default_cat)
            )
        # 默认设置
        _execute(cursor,
            "INSERT INTO settings (user_id, key, value) VALUES (?, 'default_remind_days', '3') "
            "ON CONFLICT (user_id, key) DO UPDATE SET value = '3'" if _db_type == 'postgresql' else
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, 'default_remind_days', '3')",
            (user_id,)
        )
        conn.commit()
        conn.close()
        return True, f"注册成功！欢迎，{username.strip()}"
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e).upper() or 'unique' in str(e).lower():
            return False, "用户名已存在，请换一个"
        return False, f"注册失败：{e}"


def get_user_by_username(username):
    """根据用户名获取用户"""
    conn = get_db()
    cursor = conn.cursor()
    return _fetchone(cursor, "SELECT * FROM users WHERE username = ?", (username.strip(),))


def get_user_by_id(user_id):
    """根据 ID 获取用户"""
    conn = get_db()
    cursor = conn.cursor()
    return _fetchone(cursor, "SELECT * FROM users WHERE id = ?", (user_id,))


# ==================== 待办管理 ====================

def add_todo(user_id, content, due_date=None, priority=2, remind_days=None, notes=None, tags=None, category=None):
    """添加待办"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    _execute(cursor, """
        INSERT INTO tasks (user_id, content, type, created_date, due_date, priority, status, remind_days, notes, tags, category)
        VALUES (?, ?, 'todo', ?, ?, ?, 'pending', ?, ?, ?, ?)
    """, (user_id, content.strip(), today, due_date, priority, remind_days, notes, tags, category))
    conn.commit()
    conn.close()


def add_done(user_id, content):
    """添加已完成记录"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    now = _now()
    _execute(cursor, """
        INSERT INTO tasks (user_id, content, type, created_date, completed_time, status)
        VALUES (?, ?, 'done', ?, ?, 'completed')
    """, (user_id, content.strip(), today, now))
    conn.commit()
    conn.close()


def get_todos(user_id, tag_filter=None, category_filter=None):
    """获取待办列表"""
    conn = get_db()
    cursor = conn.cursor()
    conditions = ["user_id = ?", "type = 'todo'", "status = 'pending'"]
    params = [user_id]

    if tag_filter:
        conditions.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
        params.extend([tag_filter, tag_filter + ',%', '%,' + tag_filter, '%,' + tag_filter + ',%'])

    if category_filter:
        conditions.append("category = ?")
        params.append(category_filter)

    where = " AND ".join(conditions)
    result = _fetchall(cursor,
        f"SELECT id, content, due_date, priority, created_date, remind_days, notes, tags, category "
        f"FROM tasks WHERE {where} ORDER BY priority ASC, created_date ASC",
        params
    )
    conn.close()
    return result


def get_today_done(user_id, tag_filter=None, category_filter=None):
    """获取今日完成"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    conditions = ["user_id = ?", "type = 'done'", "created_date = ?"]
    params = [user_id, today]

    if tag_filter:
        conditions.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
        params.extend([tag_filter, tag_filter + ',%', '%,' + tag_filter, '%,' + tag_filter + ',%'])

    if category_filter:
        conditions.append("category = ?")
        params.append(category_filter)

    where = " AND ".join(conditions)
    result = _fetchall(cursor,
        f"SELECT id, content, completed_time, notes, tags, category "
        f"FROM tasks WHERE {where} ORDER BY completed_time ASC",
        params
    )
    conn.close()
    return result


def get_history_done(user_id):
    """获取历史完成（今天之前）"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    result = _fetchall(cursor, """
        SELECT id, content, completed_time, created_date, notes, tags, category
        FROM tasks WHERE user_id = ? AND type = 'done' AND created_date < ?
        ORDER BY created_date DESC, completed_time DESC
    """, (user_id, today))
    conn.close()
    return result


def mark_as_done(user_id, todo_id):
    """标记为完成"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    now = _now()
    _execute(cursor, """
        UPDATE tasks SET type = 'done', status = 'completed',
        completed_time = ?, created_date = ?
        WHERE id = ? AND user_id = ?
    """, (now, today, todo_id, user_id))
    conn.commit()
    conn.close()


def revert_to_todo(user_id, done_id):
    """改回待办"""
    conn = get_db()
    cursor = conn.cursor()
    _execute(cursor, """
        UPDATE tasks SET type = 'todo', status = 'pending', completed_time = NULL
        WHERE id = ? AND user_id = ?
    """, (done_id, user_id))
    conn.commit()
    conn.close()


def delete_task(user_id, task_id):
    """删除任务"""
    conn = get_db()
    cursor = conn.cursor()
    _execute(cursor, "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit()
    conn.close()


def update_task(user_id, task_id, content=None, due_date=None, priority=None,
                remind_days=None, notes=None, tags=None, category=None):
    """更新任务"""
    conn = get_db()
    cursor = conn.cursor()
    fields = []
    params = []

    if content is not None:
        fields.append("content = ?")
        params.append(content.strip())
    if due_date is not None:
        fields.append("due_date = ?")
        params.append(due_date)
    if priority is not None:
        fields.append("priority = ?")
        params.append(priority)
    if remind_days is not None:
        fields.append("remind_days = ?")
        params.append(remind_days)
    if notes is not None:
        fields.append("notes = ?")
        params.append(notes)
    if tags is not None:
        fields.append("tags = ?")
        params.append(tags)
    if category is not None:
        fields.append("category = ?")
        params.append(category)

    if fields:
        params.extend([task_id, user_id])
        _execute(cursor, f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND user_id = ?", params)
        conn.commit()

    conn.close()


def clear_today_done(user_id):
    """清空今日完成"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    _execute(cursor, "DELETE FROM tasks WHERE user_id = ? AND type = 'done' AND created_date = ?", (user_id, today))
    conn.commit()
    conn.close()


# ==================== 统计 ====================

def get_stats(user_id, tag_filter=None, category_filter=None):
    """获取统计"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()

    def build(base):
        conds = ["user_id = ?", base]
        params = [user_id]
        if tag_filter:
            conds.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
            params.extend([tag_filter, tag_filter + ',%', '%,' + tag_filter, '%,' + tag_filter + ',%'])
        if category_filter:
            conds.append("category = ?")
            params.append(category_filter)
        return " AND ".join(conds), params

    w1, p1 = build(f"type = 'done' AND created_date = ?")
    p1.append(today)
    row = _fetchone(cursor, f"SELECT COUNT(*) as count FROM tasks WHERE {w1}", p1)
    done_count = row['count'] if row else 0

    w2, p2 = build("type = 'todo' AND status = 'pending'")
    row = _fetchone(cursor, f"SELECT COUNT(*) as count FROM tasks WHERE {w2}", p2)
    todo_count = row['count'] if row else 0

    conn.close()
    return {'done': done_count, 'todo': todo_count}


def get_today_summary(user_id):
    """今日小结"""
    conn = get_db()
    cursor = conn.cursor()
    today = _today()
    rows = _fetchall(cursor, """
        SELECT content, completed_time FROM tasks
        WHERE user_id = ? AND type = 'done' AND created_date = ?
        ORDER BY completed_time ASC
    """, (user_id, today))
    conn.close()

    if not rows:
        return None
    return {
        'date': today,
        'items': [r['content'] for r in rows],
        'count': len(rows)
    }


def get_weekly_stats(user_id):
    """本周统计"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    result = []

    conn = get_db()
    cursor = conn.cursor()
    for i in range(7):
        date_obj = monday + timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')
        row = _fetchone(cursor,
            "SELECT COUNT(*) as count FROM tasks WHERE user_id = ? AND type = 'done' AND created_date = ?",
            (user_id, date_str)
        )
        count = row['count'] if row else 0
        result.append({'date': date_str, 'weekday': weekdays[i], 'count': count})
    conn.close()
    return result


# ==================== 标签 ====================

def get_all_tags(user_id):
    """获取所有标签"""
    conn = get_db()
    cursor = conn.cursor()
    rows = _fetchall(cursor,
        "SELECT DISTINCT tags FROM tasks WHERE user_id = ? AND tags IS NOT NULL AND tags != ''",
        (user_id,))
    conn.close()

    all_tags = set()
    for row in rows:
        if row['tags']:
            for tag in row['tags'].split(','):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
    return sorted(list(all_tags))


# ==================== 分类 ====================

def get_all_categories(user_id):
    """获取所有分类"""
    conn = get_db()
    cursor = conn.cursor()
    rows = _fetchall(cursor,
        "SELECT name FROM categories WHERE user_id = ? ORDER BY id ASC",
        (user_id,))
    conn.close()
    return [r['name'] for r in rows]


def add_category(user_id, name):
    """添加分类"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        _execute(cursor, "INSERT INTO categories (user_id, name) VALUES (?, ?)", (user_id, name.strip()))
        conn.commit()
        conn.close()
        return True, f"分类「{name.strip()}」已添加"
    except Exception:
        conn.close()
        return False, f"分类「{name.strip()}」已存在"


def delete_category(user_id, name):
    """删除分类"""
    conn = get_db()
    cursor = conn.cursor()
    _execute(cursor, "UPDATE tasks SET category = NULL WHERE user_id = ? AND category = ?", (user_id, name))
    _execute(cursor, "DELETE FROM categories WHERE user_id = ? AND name = ?", (user_id, name))
    conn.commit()
    conn.close()


def rename_category(user_id, old_name, new_name):
    """重命名分类"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        _execute(cursor, "UPDATE tasks SET category = ? WHERE user_id = ? AND category = ?",
                 (new_name.strip(), user_id, old_name))
        _execute(cursor, "UPDATE categories SET name = ? WHERE user_id = ? AND name = ?",
                 (new_name.strip(), user_id, old_name))
        conn.commit()
        conn.close()
        return True, f"分类已重命名为「{new_name.strip()}」"
    except Exception:
        conn.close()
        return False, f"分类「{new_name.strip()}」已存在"


# ==================== 设置 ====================

def get_setting(user_id, key, default=None):
    """获取设置"""
    conn = get_db()
    cursor = conn.cursor()
    row = _fetchone(cursor, "SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
    conn.close()
    return row['value'] if row else default


def save_setting(user_id, key, value):
    """保存设置"""
    conn = get_db()
    cursor = conn.cursor()
    if _db_type == 'postgresql':
        _execute(cursor,
            "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, key) DO UPDATE SET value = ?",
            (user_id, key, str(value), str(value)))
    else:
        _execute(cursor,
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
            (user_id, key, str(value)))
    conn.commit()
    conn.close()


# ==================== 提醒 ====================

def get_reminder_tasks(user_id):
    """获取需提醒的任务"""
    conn = get_db()
    cursor = conn.cursor()

    default_days = 3
    row = _fetchone(cursor,
        "SELECT value FROM settings WHERE user_id = ? AND key = 'default_remind_days'",
        (user_id,))
    if row:
        default_days = int(row['value'])

    rows = _fetchall(cursor, """
        SELECT id, content, due_date, remind_days, last_reminded_date
        FROM tasks WHERE user_id = ? AND type = 'todo' AND status = 'pending' AND due_date IS NOT NULL
    """, (user_id,))
    conn.close()

    reminder_tasks = []
    today = datetime.now().strftime('%Y-%m-%d')
    for task in rows:
        actual_remind_days = task['remind_days'] if task['remind_days'] is not None else default_days
        if actual_remind_days <= 0:
            continue
        if task['due_date'] and task['due_date'] != 'None':
            try:
                due = datetime.strptime(task['due_date'], '%Y-%m-%d')
                days_left = (due - datetime.now()).days
            except:
                continue
        else:
            continue

        if days_left <= actual_remind_days:
            last_reminded = task['last_reminded_date']
            if last_reminded != today and last_reminded != 'None':
                reminder_tasks.append({
                    'id': task['id'],
                    'content': task['content'],
                    'due_date': task['due_date'],
                    'days_left': days_left
                })
    return reminder_tasks


def mark_reminded(user_id, task_ids):
    """标记已提醒"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    for tid in task_ids:
        _execute(cursor, "UPDATE tasks SET last_reminded_date = ? WHERE id = ? AND user_id = ?",
                 (today, tid, user_id))
    conn.commit()
    conn.close()


# ==================== 数据迁移 ====================

def migrate_to_supabase(supabase_url):
    """
    将当前数据库中的所有数据迁移到 Supabase PostgreSQL。
    返回 {'success': bool, 'report': str, 'details': dict}
    """
    if not HAS_PSYCOPG2:
        return {'success': False, 'report': '未安装 psycopg2，无法连接 PostgreSQL', 'details': {}}

    old_conn = get_db()
    old_type = _db_type
    old_cursor = old_conn.cursor()

    new_conn = psycopg2.connect(supabase_url)
    new_cursor = new_conn.cursor()

    details = {}

    try:
        # ---- 在 Supabase 中建表 ----
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )
        """)
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('todo', 'done')),
                created_date TEXT NOT NULL,
                completed_time TEXT,
                due_date TEXT,
                priority INTEGER DEFAULT 2 CHECK(priority IN (1, 2, 3)),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                remind_days INTEGER,
                last_reminded_date TEXT,
                notes TEXT,
                tags TEXT,
                category TEXT
            )
        """)
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_reminder (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                reminded INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(user_id, name)
            )
        """)
        new_conn.commit()

        # ---- 迁移 users ----
        old_rows = _fetchall_any(old_cursor, old_type, "SELECT * FROM users ORDER BY id ASC")
        user_id_map = {}  # old_id -> new_id
        user_count = 0

        for row in old_rows:
            new_cursor.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
                (row['username'], row['password_hash'], row.get('created_at', ''))
            )
            new_id = new_cursor.fetchone()[0]
            user_id_map[row['id']] = new_id
            user_count += 1

        details['users'] = user_count

        # ---- 迁移 categories ----
        old_rows = _fetchall_any(old_cursor, old_type, "SELECT * FROM categories ORDER BY id ASC")
        cat_count = 0
        for row in old_rows:
            new_uid = user_id_map.get(row['user_id'])
            if new_uid:
                try:
                    new_cursor.execute(
                        "INSERT INTO categories (user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (new_uid, row['name'])
                    )
                    cat_count += 1
                except Exception:
                    pass
        details['categories'] = cat_count

        # ---- 迁移 tasks ----
        old_rows = _fetchall_any(old_cursor, old_type, "SELECT * FROM tasks ORDER BY id ASC")
        task_count = 0
        for row in old_rows:
            new_uid = user_id_map.get(row['user_id'])
            if new_uid:
                new_cursor.execute(
                    """INSERT INTO tasks
                    (user_id, content, type, created_date, completed_time, due_date,
                     priority, status, remind_days, last_reminded_date, notes, tags, category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (new_uid, row['content'], row['type'], row['created_date'],
                     row.get('completed_time'), row.get('due_date'), row.get('priority', 2),
                     row.get('status', 'pending'), row.get('remind_days'),
                     row.get('last_reminded_date'), row.get('notes'), row.get('tags'),
                     row.get('category'))
                )
                task_count += 1
        details['tasks'] = task_count

        # ---- 迁移 settings ----
        old_rows = _fetchall_any(old_cursor, old_type, "SELECT * FROM settings")
        set_count = 0
        for row in old_rows:
            new_uid = user_id_map.get(row['user_id'])
            if new_uid:
                try:
                    new_cursor.execute(
                        "INSERT INTO settings (user_id, key, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (new_uid, row['key'], row['value'])
                    )
                    set_count += 1
                except Exception:
                    pass
        details['settings'] = set_count

        # ---- 迁移 daily_reminder ----
        old_rows = _fetchall_any(old_cursor, old_type, "SELECT * FROM daily_reminder")
        dr_count = 0
        for row in old_rows:
            new_uid = user_id_map.get(row['user_id'])
            if new_uid:
                try:
                    new_cursor.execute(
                        "INSERT INTO daily_reminder (user_id, date, reminded) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (new_uid, row['date'], row.get('reminded', 0))
                    )
                    dr_count += 1
                except Exception:
                    pass
        details['daily_reminders'] = dr_count

        new_conn.commit()

        report = (f"迁移完成！\n"
                  f"用户: {user_count} | 任务: {task_count} | "
                  f"分类: {cat_count} | 设置: {set_count} | 提醒记录: {dr_count}")

        return {'success': True, 'report': report, 'details': details}

    except Exception as e:
        new_conn.rollback()
        return {'success': False, 'report': f'迁移失败: {str(e)}', 'details': details}
    finally:
        old_conn.close()
        new_conn.close()


def _fetchall_any(cursor, db_type, sql, params=None):
    """通用查询多行，返回 list[dict]（不依赖全局 _db_type）"""
    if params:
        if db_type == 'postgresql':
            sql = sql.replace('?', '%s')
        cursor.execute(sql, params)
    else:
        if db_type == 'postgresql':
            sql = sql.replace('?', '%s')
        cursor.execute(sql)

    rows = cursor.fetchall()
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in rows]
