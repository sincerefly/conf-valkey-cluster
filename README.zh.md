# conf-valkey-cluster

[English](README.md)

用于 **macOS + OrbStack** 本地开发的六节点 Valkey 集群：三主三副本，使用 host 网络和 loopback 地址。其他环境未测试，不用于生产部署。

## 快速开始

需要已启动的 OrbStack、Docker Compose 和 Python 3.10+。

```bash
git clone https://github.com/sincerefly/conf-valkey-cluster.git
cd conf-valkey-cluster
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x init.sh start.sh stop.sh test.sh

./init.sh       # 创建集群，已有集群则检查状态
./stop.sh       # 停止容器，保留数据
./start.sh      # 重新启动已初始化的集群
```

脚本自动使用 `.venv/bin/python`，无需激活虚拟环境。请通过脚本启动，不直接用 `docker compose up`，避免绕过启动检查。

| 配置 | 默认值 |
| --- | --- |
| 镜像 | `valkey/valkey:7.2.14-alpine` |
| 客户端端口 | `7100–7105` |
| Cluster bus 端口 | `17100–17105` |
| 数据 | `./data/local/node-0` 至 `node-5`，启用 AOF |
| Compose 项目 | `valkey-cluster` |

## 连接与检查

在仓库目录执行：

```bash
# 只读检查六个节点的健康状态
.venv/bin/python redis_cluster_test.py --health

# 跨三个主节点读写测试
.venv/bin/python redis_cluster_test.py

# 可选，需要本机已安装 redis-cli
redis-cli -c -h 127.0.0.1 -p 7100

# 查看状态和日志
docker compose ps
docker compose logs --tail=100
```

读写测试使用唯一临时键，结束后删除，并设置 60 秒过期时间。检查失败返回非零；每个阶段默认限时 60 秒，可用 `--timeout 30` 调整。启动检查失败时容器可能仍在运行，重试前先查看日志。

## 自定义配置

在 shell 中 `export`，不要修改 `.env`。例如另外启动一套集群：

```bash
export VALKEY_IMAGE=valkey/valkey:9.1.2-alpine
export VALKEY_BASE_PORT=7200
export VALKEY_DATA_DIR="$PWD/data/valkey-9.1.2"
export COMPOSE_PROJECT_NAME=valkey-cluster-9-1-2

./init.sh
.venv/bin/python redis_cluster_test.py --health
./stop.sh

unset VALKEY_IMAGE VALKEY_BASE_PORT VALKEY_DATA_DIR COMPOSE_PROJECT_NAME
```

基础端口对应连续六个客户端端口，bus 端口为客户端端口 + 10000。后续检查、启停保持相同的环境变量。多套集群需要独立的项目名、端口和数据目录。脚本支持短镜像标签，原始 Compose 命令需使用完整镜像名；自定义端口由脚本计算，不能直接用原始 Compose 代替。

**保留已有数据：** 目录中已有持久化文件时，更换镜像或基础端口需要使用新数据目录。迁移前先备份；脚本不自动升级、重置或迁移数据。原来的 `data/7000`～`data/7005` 和旧部署不由新默认配置管理。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
./test.sh                          # 测试 7.2.14-alpine 和 9.1.2-alpine
./test.sh 9.1.2-alpine              # 测试指定版本
```

集成测试使用临时项目和数据目录，端口为 `27100–27105`、`37100–37105`，冲突时可设置 `VALKEY_TEST_BASE_PORT`。测试覆盖重复初始化、宿主机读写及重启后的持久性。容器停止成功后才删除测试数据，清理失败会保留数据并报错。两个默认版本已在 OrbStack 上测试，不代表已有数据的升级兼容性。
