# 网页围棋 · KataGo

网页版人机围棋游戏，使用 KataGo Eigen（纯 CPU）作为 AI 引擎，适合部署在 1GB 内存的 Linux VPS。

## 技术栈

| 层 | 技术 |
|----|------|
| AI 引擎 | KataGo Eigen (CPU-only, b6c96 小模型) |
| 后端 | Python 3 + Flask（轻量，约 30 MB RAM） |
| 前端 | 纯 HTML/CSS/JS + Canvas（无框架依赖） |
| 通信 | REST API（JSON） |

## 内存占用估算（1GB VPS）

| 组件 | 估算 RAM |
|------|---------|
| KataGo + b6c96 模型 | ~150 MB |
| Python/Flask | ~40 MB |
| 系统 | ~200 MB |
| **合计** | **~400 MB** |

## 快速部署

```bash
# 1. 克隆仓库
git clone <repo-url>
cd jinchaoapp

# 2. 一键安装（下载 KataGo 二进制 + b6c96 模型 + Python 依赖）
bash setup.sh

# 3. 启动服务
bash start.sh
```

浏览器访问 `http://<VPS-IP>:5000`

## 目录结构

```
.
├── app.py              # Flask 后端（REST API）
├── katago_gtp.py       # KataGo GTP 协议接口
├── config/
│   └── gtp.cfg         # KataGo 配置（低内存优化）
├── frontend/
│   ├── index.html      # 页面
│   ├── style.css       # 样式
│   └── game.js         # 棋盘渲染 + 游戏逻辑
├── katago_bin/         # KataGo 二进制（由 setup.sh 下载）
├── models/             # 棋型文件（由 setup.sh 下载）
├── setup.sh            # 安装脚本
├── start.sh            # 启动脚本
├── .env.example        # 环境变量示例
└── requirements.txt
```

## 配置说明（config/gtp.cfg）

关键参数（已针对 1GB VPS 优化）：

```ini
numSearchThreads = 1   # 单线程搜索，减少 CPU/内存占用
maxVisits = 200        # 每步最多搜索 200 次（更高 = 更强但更慢）
nnCacheSizePowerOfTwo = 17  # 神经网络缓存（可减小到 15 以节省内存）
```

若内存仍然紧张，可将 `nnCacheSizePowerOfTwo` 从 17 改为 15（缓存从 128K 降至 32K 条目）。

## 更换更强的模型

```bash
# 下载 b15c192 模型（更强，~500 MB RAM）
curl -L -o models/model.bin.gz \
  https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b15c192-s1672170752-d466197061.bin.gz
```

## 使用 systemd 开机自启

```ini
# /etc/systemd/system/weiqi.service
[Unit]
Description=Web Go Game (KataGo)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/jinchaoapp
EnvironmentFile=/home/ubuntu/jinchaoapp/.env
ExecStart=/usr/bin/python3 /home/ubuntu/jinchaoapp/app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now weiqi
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/status` | 获取当前游戏状态 |
| POST | `/api/new_game` | 开始新对局 |
| POST | `/api/play` | 人类落子 `{"vertex": "D4"}` |
| POST | `/api/pass` | 虚手 |
| POST | `/api/resign` | 认输 |
