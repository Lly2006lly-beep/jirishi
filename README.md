# 今日事 Web

一个简约文艺的多用户待办管理 Web 应用，支持手机和电脑浏览器访问。

## 功能特性

- 👥 **多用户支持** — 注册/登录/注销，数据完全隔离
- 📝 **待办管理** — 添加、编辑、删除待办事项，支持优先级、分类、标签
- ✅ **工作记录** — 标记完成、手动记录完成的工作，支持改回待办
- 📂 **分类管理** — 自定义分类，重命名、删除
- 🏷️ **标签系统** — 多标签支持，按标签筛选
- 📅 **截止日期提醒** — 登录后在首页顶部温和提醒即将到期的待办
- 📊 **每日小结** — 生成 Markdown 小结，支持复制和下载
- 📈 **每周统计** — 可视化本周每日完成数量
- 📱 **移动优先** — 响应式设计，手机端完美适配，无横向滚动条
- 🎨 **文艺简约** — 暖纸色背景，柔和阴影，舒适阅读体验
- 🔒 **安全** — 密码哈希存储，SQL 参数化查询防注入

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask 3.x |
| 用户认证 | Flask-Login + Werkzeug 密码哈希 |
| 数据库 | SQLite（可切换 PostgreSQL/MySQL） |
| 前端 | 纯 HTML + CSS + 少量 JS（无框架依赖） |
| 部署 | gunicorn + Render.com |

## 项目结构

```
web/
├── app.py              # Flask 主应用（路由、认证、业务逻辑）
├── models.py           # 数据库模型层（多用户 SQL 操作）
├── requirements.txt    # Python 依赖
├── README.md           # 项目说明
├── templates/          # HTML 模板
│   ├── base.html       # 基础模板（导航栏、页脚）
│   ├── index.html      # 首页（待办列表 + 今日完成）
│   ├── login.html      # 登录页
│   ├── register.html   # 注册页
│   ├── reminders.html  # 提醒详情页
│   ├── categories.html # 分类管理页
│   ├── history.html    # 历史记录页
│   ├── summary.html    # 每日小结页
│   └── settings.html   # 设置页
└── static/
    └── style.css       # 全局样式表
```

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化并运行

```bash
cd web
python app.py
```

首次运行会自动创建 `tasks.db` 数据库文件。

### 3. 打开浏览器

访问 http://localhost:5000

- 点击「立即注册」创建账户
- 登录后即可使用全部功能

## 部署到 Render.com（免费）

Render.com 提供免费的 Web Service 托管。

### 步骤

1. **注册** [Render.com](https://render.com) 账户

2. **创建 Web Service**：选择「New +」→「Web Service」

3. **连接 GitHub 仓库**（或上传项目）

4. **配置如下**：

| 配置项 | 值 |
|--------|-----|
| Name | jirishi（或自定义） |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT` |
| Instance Type | Free |

5. **设置环境变量**（可选）：

| Key | Value |
|-----|-------|
| SECRET_KEY | 一串随机字符串（如 `openssl rand -hex 32` 生成） |
| FLASK_DEBUG | 0 |

6. 点击「Create Web Service」，等待部署完成

部署后即可通过 `https://你的服务名.onrender.com` 访问。

> **注意**：免费实例在 15 分钟无请求后会休眠，首次访问可能需要等待约 30 秒唤醒。SQLite 数据在免费实例上不是持久化的（实例重启会丢失），如需持久化请升级到付费计划或使用外部数据库。

## 数据库说明

- 默认使用 SQLite，数据库文件为 `web/tasks.db`
- 如需切换到 PostgreSQL（推荐生产环境），修改 `models.py` 中的 `get_db()` 函数即可
- 所有表均包含 `user_id` 字段，确保多用户数据隔离

## 安全性

- 密码使用 `werkzeug.security.generate_password_hash` 哈希存储
- 所有 SQL 查询使用参数化查询，防止 SQL 注入
- 用户输入做基本验证（长度、格式）
- 每个操作均校验 `user_id`，防止越权访问
