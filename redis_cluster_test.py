#!/usr/bin/env python3
import sys
import time
from redis.cluster import RedisCluster
from redis.exceptions import RedisError


# Usage: 
#   python3 -m venv venv
#   source venv/bin/activate
#   python3 redis_cluster_test.py

NODES = [
    ("127.0.0.1", 7000),
    ("127.0.0.1", 7001),
    ("127.0.0.1", 7002),
    ("127.0.0.1", 7003),
    ("127.0.0.1", 7004),
    ("127.0.0.1", 7005),
]

def main():
    print("🔍 Connecting to cluster via first node...")
    try:
        rc = RedisCluster(host=NODES[0][0], port=NODES[0][1], decode_responses=True)
        print("✅ Connected successfully!")
    except RedisError as e:
        print("❌ Failed to connect:", e)
        sys.exit(1)

    # 写入/读取测试
    key = "cluster:test"
    val = "Hello Cluster"
    rc.set(key, val)
    got = rc.get(key)
    print(f"📝 SET {key}='{val}' → GET='{got}'")

    # 各节点 PING 测试
    print("\n📡 Node PING test:")
    for host, port in NODES:
        start = time.time()
        try:
            tmp = RedisCluster(host=host, port=port, decode_responses=True)
            tmp.ping()
            ms = (time.time() - start) * 1000
            print(f"  {host}:{port:<5} ✅ {ms:.1f} ms")
        except Exception as e:
            print(f"  {host}:{port:<5} ❌ {type(e).__name__}")

if __name__ == "__main__":
    main()
