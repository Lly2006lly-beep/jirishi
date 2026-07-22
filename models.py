# -*- coding: utf-8 -*-
"""
今日事 Web - 数据库模型
基于原桌面版 DatabaseManager 改造，增加多用户支持（user_id 关联）。
所有 SQL 操作使用参数化查询，防止 SQL 注入。
"""

import sqlite3
from datetime import datetime, timedelta


def get_db():
    """获取数据库连接（使用 row_factory 以便通过列名访问）"""
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库：创建所有表和默认数据"""
    conn = get_db()
    cursor = conn.cursor()

    # ==================== 用户表 ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        )
    """)

    # ==================== 任务表（多用户：通过 user_id 关联） ====================
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

    # ==================== 用户设置表 ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ==================== 每日提醒表 ====================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_reminder (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reminded INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ==================== 分类表 ====================
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
    """创建新用户，返回 (success, message)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username.strip(), password_hash)
        )
        user_id = cursor.lastrowid
        conn.commit()

        # 为新用户创建默认分类
        for default_cat in ['工作', '学习', '生活']:
            cursor.execute(
                "INSERT OR IGNORE INTO categories (user_id, name) VALUES (?, ?)",
                (user_id, default_cat)
            )
        # 设置默认提醒天数
        cursor.execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, 'default_remind_days', '3')",
            (user_id,)
        )
        conn.commit()
        conn.close()
        return True, f"注册成功！欢迎，{username.strip()}"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "用户名已存在，请换一个"


def get_user_by_username(username):
    """根据用户名获取用户信息"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    """根据用户 ID 获取用户信息"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


# ==================== 待办管理（多用户） ====================

def add_todo(user_id, content, due_date=None, priority=2, remind_days=None, notes=None, tags=None, category=None):
    """添加一条待办事项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (user_id, content, type, created_date, due_date, priority, status, remind_days, notes, tags, category)
        VALUES (?, ?, 'todo', DATE('now'), ?, ?, 'pending', ?, ?, ?, ?)
    """, (user_id, content.strip(), due_date, priority, remind_days, notes, tags, category))
    conn.commit()
    conn.close()


def add_done(user_id, content):
    """直接添加一条已完成的工作记录"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (user_id, content, type, created_date, completed_time, status)
        VALUES (?, ?, 'done', DATE('now'), DATETIME('now'), 'completed')
    """, (user_id, content.strip()))
    conn.commit()
    conn.close()


def get_todos(user_id, tag_filter=None, category_filter=None):
    """获取用户的所有待办事项"""
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

    where_clause = " AND ".join(conditions)
    cursor.execute(f"""
        SELECT id, content, due_date, priority, created_date, remind_days, notes, tags, category
        FROM tasks WHERE {where_clause}
        ORDER BY priority ASC, created_date ASC
    """, params)
    todos = cursor.fetchall()
    conn.close()
    return todos


def get_today_done(user_id, tag_filter=None, category_filter=None):
    """获取用户今日已完成的工作"""
    conn = get_db()
    cursor = conn.cursor()
    conditions = ["user_id = ?", "type = 'done'", "created_date = DATE('now')"]
    params = [user_id]

    if tag_filter:
        conditions.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
        params.extend([tag_filter, tag_filter + ',%', '%,' + tag_filter, '%,' + tag_filter + ',%'])

    if category_filter:
        conditions.append("category = ?")
        params.append(category_filter)

    where_clause = " AND ".join(conditions)
    cursor.execute(f"""
        SELECT id, content, completed_time, notes, tags, category
        FROM tasks WHERE {where_clause}
        ORDER BY completed_time ASC
    """, params)
    done_items = cursor.fetchall()
    conn.close()
    return done_items


def get_history_done(user_id):
    """获取用户历史完成记录（今天之前）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, content, completed_time, created_date, notes, tags, category
        FROM tasks
        WHERE user_id = ? AND type = 'done' AND created_date < DATE('now')
        ORDER BY created_date DESC, completed_time DESC
    """, (user_id,))
    items = cursor.fetchall()
    conn.close()
    return items


def mark_as_done(user_id, todo_id):
    """将待办标记为已完成（更新 created_date 为今天，使其出现在今日完成栏）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET type = 'done', status = 'completed',
        completed_time = DATETIME('now'), created_date = DATE('now')
        WHERE id = ? AND user_id = ?
    """, (todo_id, user_id))
    conn.commit()
    conn.close()


def revert_to_todo(user_id, done_id):
    """将已完成的工作改回待办"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET type = 'todo', status = 'pending', completed_time = NULL
        WHERE id = ? AND user_id = ?
    """, (done_id, user_id))
    conn.commit()
    conn.close()


def delete_task(user_id, task_id):
    """删除任务"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit()
    conn.close()


def update_task(user_id, task_id, content=None, due_date=None, priority=None,
                remind_days=None, notes=None, tags=None, category=None):
    """更新任务信息（只更新提供的字段）"""
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
        cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND user_id = ?", params)
        conn.commit()

    conn.close()


def clear_today_done(user_id):
    """清空用户今日完成的所有工作"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE user_id = ? AND type = 'done' AND created_date = DATE('now')", (user_id,))
    conn.commit()
    conn.close()


# ==================== 统计与汇总 ====================

def get_stats(user_id, tag_filter=None, category_filter=None):
    """获取用户统计信息"""
    conn = get_db()
    cursor = conn.cursor()

    def build_query(base_condition):
        conditions = ["user_id = ?", base_condition]
        params = [user_id]
        if tag_filter:
            conditions.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
            params.extend([tag_filter, tag_filter + ',%', '%,' + tag_filter, '%,' + tag_filter + ',%'])
        if category_filter:
            conditions.append("category = ?")
            params.append(category_filter)
        return " AND ".join(conditions), params

    where_done, done_params = build_query("type = 'done' AND created_date = DATE('now')")
    cursor.execute(f"SELECT COUNT(*) as count FROM tasks WHERE {where_done}", done_params)
    done_count = cursor.fetchone()['count']

    where_todo, todo_params = build_query("type = 'todo' AND status = 'pending'")
    cursor.execute(f"SELECT COUNT(*) as count FROM tasks WHERE {where_todo}", todo_params)
    todo_count = cursor.fetchone()['count']

    conn.close()
    return {'done': done_count, 'todo': todo_count}


def get_today_summary(user_id):
    """获取用户今日小结"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content, completed_time FROM tasks
        WHERE user_id = ? AND type = 'done' AND created_date = DATE('now')
        ORDER BY completed_time ASC
    """, (user_id,))
    done_items = cursor.fetchall()
    conn.close()

    if not done_items:
        return None

    today_date = datetime.now().strftime('%Y-%m-%d')
    return {
        'date': today_date,
        'items': [item['content'] for item in done_items],
        'count': len(done_items)
    }


def get_weekly_stats(user_id):
    """获取用户本周每天的完成统计"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    result = []

    conn = get_db()
    cursor = conn.cursor()
    for i in range(7):
        date_obj = monday + timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE user_id = ? AND type = 'done' AND created_date = ?",
            (user_id, date_str)
        )
        count = cursor.fetchone()['count']
        result.append({'date': date_str, 'weekday': weekdays[i], 'count': count})
    conn.close()
    return result


# ==================== 标签管理 ====================

def get_all_tags(user_id):
    """获取用户所有标签"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT tags FROM tasks WHERE user_id = ? AND tags IS NOT NULL AND tags != ''", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    all_tags = set()
    for row in rows:
        if row['tags']:
            for tag in row['tags'].split(','):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
    return sorted(list(all_tags))


# ==================== 分类管理 ====================

def get_all_categories(user_id):
    """获取用户所有分类"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['name'] for row in rows]


def add_category(user_id, name):
    """添加分类，返回 (success, message)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)", (user_id, name.strip()))
        conn.commit()
        conn.close()
        return True, f"分类「{name.strip()}」已添加"
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"分类「{name.strip()}」已存在"


def delete_category(user_id, name):
    """删除分类"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET category = NULL WHERE user_id = ? AND category = ?", (user_id, name))
    cursor.execute("DELETE FROM categories WHERE user_id = ? AND name = ?", (user_id, name))
    conn.commit()
    conn.close()


def rename_category(user_id, old_name, new_name):
    """重命名分类，返回 (success, message)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE tasks SET category = ? WHERE user_id = ? AND category = ?",
                       (new_name.strip(), user_id, old_name))
        cursor.execute("UPDATE categories SET name = ? WHERE user_id = ? AND name = ?",
                       (new_name.strip(), user_id, old_name))
        conn.commit()
        conn.close()
        return True, f"分类已重命名为「{new_name.strip()}」"
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"分类「{new_name.strip()}」已存在"


# ==================== 设置管理 ====================

def get_setting(user_id, key, default=None):
    """获取用户设置"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
    result = cursor.fetchone()
    conn.close()
    return result['value'] if result else default


def save_setting(user_id, key, value):
    """保存用户设置"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
                   (user_id, key, str(value)))
    conn.commit()
    conn.close()


# ==================== 提醒功能 ====================

def get_reminder_tasks(user_id):
    """获取需要提醒的待办任务（即将到期）"""
    conn = get_db()
    cursor = conn.cursor()

    # 获取默认提醒天数
    cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = 'default_remind_days'", (user_id,))
    result = cursor.fetchone()
    default_days = int(result['value']) if result else 3

    cursor.execute("""
        SELECT id, content, due_date, remind_days, last_reminded_date,
               CAST(julianday(due_date) - julianday('now') AS INTEGER) as days_left
        FROM tasks
        WHERE user_id = ? AND type = 'todo' AND status = 'pending' AND due_date IS NOT NULL
    """, (user_id,))
    tasks = cursor.fetchall()
    conn.close()

    reminder_tasks = []
    today = datetime.now().strftime('%Y-%m-%d')
    for task in tasks:
        actual_remind_days = task['remind_days'] if task['remind_days'] is not None else default_days
        if actual_remind_days <= 0:
            continue
        days_left = task['days_left']
        if days_left is not None and days_left <= actual_remind_days:
            last_reminded = task['last_reminded_date']
            if last_reminded != today:
                reminder_tasks.append({
                    'id': task['id'],
                    'content': task['content'],
                    'due_date': task['due_date'],
                    'days_left': days_left
                })
    return reminder_tasks


def mark_reminded(user_id, task_ids):
    """标记任务已提醒"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    for task_id in task_ids:
        cursor.execute("UPDATE tasks SET last_reminded_date = ? WHERE id = ? AND user_id = ?",
                       (today, task_id, user_id))
    conn.commit()
    conn.close()
