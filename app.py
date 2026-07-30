# -*- coding: utf-8 -*-
"""
今日事 Web - Flask 主应用
一个多用户待办管理 Web 应用，支持注册、登录、待办管理、工作记录、分类标签、
截止日期提醒和每日小结导出。
"""

import os
import re
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, Response
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash

import models

# ==================== Flask 应用初始化 ====================

# 启动时自动初始化数据库（确保表结构存在）
models.init_db()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'jirishi-dev-secret-key-change-in-production')

# ---- 数据迁移：启动时若设了环境变量则自动迁移 ----
import sys as _sys, traceback as _tb
print(f"[DEBUG] MIGRATE_TO_SUPABASE={repr(os.environ.get('MIGRATE_TO_SUPABASE'))}", flush=True)
if os.environ.get('MIGRATE_TO_SUPABASE'):
    try:
        supabase_url = "postgresql://postgres:JQT1MTDNUVjDCOzb@db.mvqeyksjhqtxjithujlh.supabase.co:6543/postgres?sslmode=require&connect_timeout=10"
        result = models.migrate_to_supabase(supabase_url)
        print(f"\n{'='*60}\n[迁移成功] {result}\n{'='*60}\n", flush=True)
    except Exception as _e:
        print(f"\n{'='*60}\n[迁移失败-不阻塞启动]\n{_tb.format_exc()}\n{'='*60}\n", flush=True)
    _sys.stdout.flush()

# ==================== Flask-Login 初始化 ====================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录后再访问此页面'


class User(UserMixin):
    """Flask-Login 用户类"""
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    """从 session 加载用户"""
    user = models.get_user_by_id(int(user_id))
    if user:
        return User(user['id'], user['username'])
    return None


# ==================== 辅助装饰器 ====================

def redirect_if_logged_in(f):
    """已登录用户访问登录/注册页时重定向到首页"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def get_default_remind_days():
    """获取当前用户的默认提醒天数"""
    if current_user.is_authenticated:
        return int(models.get_setting(current_user.id, 'default_remind_days', '3'))
    return 3


# ==================== 输入验证 ====================

def validate_username(username):
    """验证用户名：2-20位字母、数字或中文"""
    if not username or len(username.strip()) < 2 or len(username.strip()) > 20:
        return False, "用户名需为 2-20 个字符"
    if not re.match(r'^[\w\u4e00-\u9fff]+$', username.strip()):
        return False, "用户名只能包含字母、数字、下划线和中文"
    return True, ""


def validate_password(password):
    """验证密码：至少6位"""
    if not password or len(password) < 6:
        return False, "密码至少需要 6 位"
    return True, ""


# ==================== 认证路由 ====================

@app.route('/register', methods=['GET', 'POST'])
@redirect_if_logged_in
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        # 验证用户名
        valid, msg = validate_username(username)
        if not valid:
            flash(msg, 'error')
            return render_template('register.html')

        # 验证密码
        valid, msg = validate_password(password)
        if not valid:
            flash(msg, 'error')
            return render_template('register.html')

        # 确认密码
        if password != password2:
            flash('两次输入的密码不一致', 'error')
            return render_template('register.html')

        # 创建用户
        password_hash = generate_password_hash(password)
        success, message = models.create_user(username, password_hash)

        if success:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@redirect_if_logged_in
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html')

        user = models.get_user_by_username(username.strip())
        if user and check_password_hash(user['password_hash'], password):
            login_user(User(user['id'], user['username']))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """用户注销"""
    logout_user()
    flash('已安全退出', 'success')
    return redirect(url_for('login'))


# ==================== 主页面 ====================

@app.route('/')
@login_required
def index():
    """首页：待办列表 + 今日完成 + 提醒"""
    user_id = current_user.id

    # 获取筛选参数
    tag_filter = request.args.get('tag', '')
    category_filter = request.args.get('category', '')

    # 获取数据
    todos = models.get_todos(user_id, tag_filter or None, category_filter or None)
    done_items = models.get_today_done(user_id, tag_filter or None, category_filter or None)
    stats = models.get_stats(user_id, tag_filter or None, category_filter or None)
    reminders = models.get_reminder_tasks(user_id)
    tags = models.get_all_tags(user_id)
    categories = models.get_all_categories(user_id)
    default_remind_days = int(models.get_setting(user_id, 'default_remind_days', '3'))

    return render_template(
        'index.html',
        todos=todos,
        done_items=done_items,
        stats=stats,
        reminders=reminders,
        tags=tags,
        categories=categories,
        current_tag=tag_filter,
        current_category=category_filter,
        today_str=datetime.now().strftime('%Y-%m-%d'),
        default_remind_days=default_remind_days
    )


# ==================== 待办操作 API ====================

@app.route('/todo/add', methods=['POST'])
@login_required
def todo_add():
    """添加待办事项"""
    content = request.form.get('content', '').strip()
    if not content:
        flash('请输入待办内容', 'error')
        return redirect(url_for('index'))

    due_date = request.form.get('due_date', '') or None
    priority = int(request.form.get('priority', 2))
    remind_days = request.form.get('remind_days', '')
    remind_days = int(remind_days) if remind_days else None
    notes = request.form.get('notes', '') or None
    tags = request.form.get('tags', '') or None
    category = request.form.get('category', '') or None

    models.add_todo(current_user.id, content, due_date, priority, remind_days, notes, tags, category)
    flash('待办已添加', 'success')
    return redirect(url_for('index'))


@app.route('/todo/<int:todo_id>/done', methods=['POST'])
@login_required
def todo_mark_done(todo_id):
    """标记待办为已完成"""
    models.mark_as_done(current_user.id, todo_id)
    flash('已标记为完成', 'success')
    return redirect(url_for('index'))


@app.route('/todo/<int:todo_id>/delete', methods=['POST'])
@login_required
def todo_delete(todo_id):
    """删除待办事项"""
    models.delete_task(current_user.id, todo_id)
    flash('待办已删除', 'success')
    return redirect(url_for('index'))


@app.route('/todo/<int:todo_id>/edit', methods=['POST'])
@login_required
def todo_edit(todo_id):
    """编辑待办事项"""
    content = request.form.get('content', '').strip()
    due_date = request.form.get('due_date', '') or None
    priority = request.form.get('priority', '')
    remind_days = request.form.get('remind_days', '')
    notes = request.form.get('notes', '') or None
    tags = request.form.get('tags', '') or None
    category = request.form.get('category', '') or None

    models.update_task(
        current_user.id, todo_id,
        content=content if content else None,
        due_date=due_date,
        priority=int(priority) if priority else None,
        remind_days=int(remind_days) if remind_days else None,
        notes=notes,
        tags=tags,
        category=category
    )
    flash('待办已更新', 'success')
    return redirect(url_for('index'))


@app.route('/done/<int:done_id>/revert', methods=['POST'])
@login_required
def done_revert(done_id):
    """将已完成工作改回待办"""
    models.revert_to_todo(current_user.id, done_id)
    flash('已改回待办', 'success')
    return redirect(url_for('index'))


@app.route('/done/<int:done_id>/delete', methods=['POST'])
@login_required
def done_delete(done_id):
    """删除已完成工作"""
    models.delete_task(current_user.id, done_id)
    flash('记录已删除', 'success')
    return redirect(url_for('index'))


@app.route('/done/add', methods=['POST'])
@login_required
def done_add():
    """直接添加已完成工作记录"""
    content = request.form.get('content', '').strip()
    if not content:
        flash('请输入工作内容', 'error')
        return redirect(url_for('index'))

    models.add_done(current_user.id, content)
    flash('工作记录已添加', 'success')
    return redirect(url_for('index'))


@app.route('/done/clear', methods=['POST'])
@login_required
def done_clear():
    """清空今日完成"""
    models.clear_today_done(current_user.id)
    flash('今日完成记录已清空', 'success')
    return redirect(url_for('index'))


# ==================== 批量操作 API ====================

@app.route('/todo/batch/done', methods=['POST'])
@login_required
def todo_batch_done():
    """批量标记待办为已完成"""
    ids = request.form.getlist('ids')
    for tid in ids:
        models.mark_as_done(current_user.id, int(tid))
    flash(f'已将 {len(ids)} 项标记为完成', 'success')
    return redirect(url_for('index'))


@app.route('/todo/batch/delete', methods=['POST'])
@login_required
def todo_batch_delete():
    """批量删除待办"""
    ids = request.form.getlist('ids')
    for tid in ids:
        models.delete_task(current_user.id, int(tid))
    flash(f'已删除 {len(ids)} 项待办', 'success')
    return redirect(url_for('index'))


# ==================== 分类管理 ====================

@app.route('/categories')
@login_required
def categories_page():
    """分类管理页面"""
    categories = models.get_all_categories(current_user.id)
    return render_template('categories.html', categories=categories)


@app.route('/category/add', methods=['POST'])
@login_required
def category_add():
    """添加分类"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('请输入分类名称', 'error')
    else:
        success, message = models.add_category(current_user.id, name)
        flash(message, 'success' if success else 'error')
    return redirect(url_for('categories_page'))


@app.route('/category/delete', methods=['POST'])
@login_required
def category_delete():
    """删除分类"""
    name = request.form.get('name', '')
    if name:
        models.delete_category(current_user.id, name)
        flash(f'分类「{name}」已删除', 'success')
    return redirect(url_for('categories_page'))


@app.route('/category/rename', methods=['POST'])
@login_required
def category_rename():
    """重命名分类"""
    old_name = request.form.get('old_name', '')
    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('请输入新名称', 'error')
    else:
        success, message = models.rename_category(current_user.id, old_name, new_name)
        flash(message, 'success' if success else 'error')
    return redirect(url_for('categories_page'))


# ==================== 提醒相关 ====================

@app.route('/reminders')
@login_required
def reminders_page():
    """提醒详情页面"""
    reminders = models.get_reminder_tasks(current_user.id)
    return render_template('reminders.html', reminders=reminders)


@app.route('/reminders/dismiss', methods=['POST'])
@login_required
def reminders_dismiss():
    """关闭提醒"""
    task_ids = request.form.getlist('ids')
    if task_ids:
        models.mark_reminded(current_user.id, [int(tid) for tid in task_ids])
    return redirect(url_for('index'))


# ==================== 每日小结导出 ====================

@app.route('/summary')
@login_required
def summary_page():
    """每日小结页面"""
    summary = models.get_today_summary(current_user.id)
    weekly = models.get_weekly_stats(current_user.id)

    if summary:
        # 生成 Markdown 小结
        md_lines = [
            f"# 今日小结",
            f"",
            f"**日期**：{summary['date']}",
            f"**完成数量**：{summary['count']} 项",
            f"",
            f"## 完成内容",
            f"",
        ]
        for i, item in enumerate(summary['items'], 1):
            md_lines.append(f"{i}. {item}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append(f"*由「今日事」自动生成*")
        summary['markdown'] = "\n".join(md_lines)

    return render_template('summary.html', summary=summary, weekly=weekly)


@app.route('/summary/download')
@login_required
def summary_download():
    """下载 Markdown 小结文件"""
    summary = models.get_today_summary(current_user.id)
    if not summary:
        flash('今天还没有完成任何工作', 'error')
        return redirect(url_for('index'))

    md_lines = [
        f"# 今日小结",
        f"",
        f"**日期**：{summary['date']}",
        f"**完成数量**：{summary['count']} 项",
        f"",
        f"## 完成内容",
        f"",
    ]
    for i, item in enumerate(summary['items'], 1):
        md_lines.append(f"{i}. {item}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append(f"*由「今日事」自动生成*")

    content = "\n".join(md_lines)
    filename = f"今日小结_{summary['date']}.md"

    return Response(
        content,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ==================== 设置 ====================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    """用户设置页面"""
    if request.method == 'POST':
        remind_days = request.form.get('remind_days', '3')
        try:
            remind_days = int(remind_days)
            if remind_days < 0:
                remind_days = 0
            models.save_setting(current_user.id, 'default_remind_days', str(remind_days))
            flash('设置已保存', 'success')
        except ValueError:
            flash('请输入有效的数字', 'error')

    remind_days = models.get_setting(current_user.id, 'default_remind_days', '3')
    return render_template('settings.html', remind_days=remind_days)


# ==================== 历史记录 ====================

@app.route('/history')
@login_required
def history_page():
    """历史完成记录页面"""
    items = models.get_history_done(current_user.id)
    return render_template('history.html', items=items)


# ==================== 启动应用 ====================

# ==================== 数据迁移路由 ====================

@app.route('/admin/migrate-to-supabase')
def migrate_to_supabase_route():
    """将当前数据库数据迁移到 Supabase PostgreSQL"""
    import traceback as _tb
    try:
        supabase_url = "postgresql://postgres:JQT1MTDNUVjDCOzb@db.mvqeyksjhqtxjithujlh.supabase.co:6543/postgres?sslmode=require&connect_timeout=10"
        result = models.migrate_to_supabase(supabase_url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'traceback': _tb.format_exc()}), 500


@app.route('/admin/export-data')
def export_data():
    """导出全部数据为JSON，用于本地迁移"""
    try:
        data = models.export_all_data()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback as _tb2
        return jsonify({'success': False, 'error': str(e), 'traceback': _tb2.format_exc()}), 500


# ==================== 启动应用 ====================

if __name__ == '__main__':
    # 首次运行时初始化数据库
    models.init_db()
    # 开发模式运行
    debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug_mode)
