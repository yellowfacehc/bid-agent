# 招投标信息查询平台 - Render 免费部署指南

## 前置准备

你需要准备以下两个免费账号：
1. **GitHub 账号**（如果没有，前往 https://github.com 注册）
2. **Render 账号**（使用 GitHub 账号直接登录 https://render.com）

---

## 第一步：下载项目文件

从 TRAE 下载压缩包 `bid_agent_project.tar.gz`，解压到本地文件夹。

---

## 第二步：上传到 GitHub

### 方法A：网页上传（最简单，无需安装任何工具）

1. 登录 GitHub，点击右上角 **+** → **New repository**
2. 仓库名填 `bid-agent`，选择 **Public**，点击 **Create repository**
3. 点击 **uploading an existing file** 链接
4. 将解压后的所有文件拖拽到上传区域（不要上传 __pycache__ 文件夹）
5. 点击 **Commit changes**

### 方法B：用命令行上传（如果已安装 Git）

```bash
cd bid_agent
git init
git add .
git commit -m "招投标信息查询平台"
git branch -M main
git remote add origin https://github.com/你的用户名/bid-agent.git
git push -u origin main
```

---

## 第三步：在 Render 上部署

1. 打开 https://dashboard.render.com 点击 **New +** → **Web Service**

2. 连接 GitHub 账号，选择你刚创建的 `bid-agent` 仓库

3. 填写部署配置：
   - **Name**: `bid-agent`（或任意名称）
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`

4. 点击 **Create Web Service**

5. 等待 2-3 分钟，Render 会自动安装依赖并启动应用

6. 部署完成后，Render 会给你一个公网链接，格式类似：
   ```
   https://bid-agent-xxxx.onrender.com
   ```

7. 这个链接任何人都能访问，手机浏览器也支持

---

## 常见问题

### Q: 部署后访问报错 500？
检查 Render 的日志（Logs 标签页），确认 gunicorn 是否安装成功。如果报错，将 Start Command 改为：
```
python app.py
```

### Q: 免费版有什么限制？
- 15分钟无访问会自动休眠，下次访问时自动唤醒（约30秒）
- 每月 750 小时免费时长
- 512MB 内存

### Q: 搜索速度慢？
这是正常的。因为需要实时爬取中国政府采购网的数据，加上反爬延迟，每次搜索约需 10-30 秒。

### Q: 如何让链接长期有效？
Render 免费版只要不删除服务，链接就永久有效。只是 15 分钟无访问会休眠。
