#!/usr/bin/env python3
"""
智能体身份证 · 签名/验签模块（Agent ID Sign/Verify）

用途：
    给「家族身份证」落地——让"我是我"可被验证。
    发消息带签名，收消息验签 → 防冒名。

机制：
    payload = f"{from}|{message}|{ts}"
    sig = Ed25519 sign(priv, payload)
    消息附加：address, sig
    收方：verify(pub, payload, sig)

技术选型：
    Ed25519（快、安全、密钥短）
    依赖：cryptography（pip install cryptography）

用法：
    # 生成密钥对
    python3 agent_id.py gen

    # 签名一条消息
    python3 agent_id.py sign "from|msg|ts" <私钥hex>

    # 验证
    python3 agent_id.py verify "from|msg|ts" <签名hex> <公钥hex>
"""

import base64
import hashlib
import os
import sys
from datetime import datetime, timezone


def _ensure_crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey, Ed25519PublicKey)
        return True
    except ImportError:
        print("需要: pip install cryptography")
        return False


def gen_keypair() -> dict:
    """生成 Ed25519 密钥对。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)

    priv_hex = priv_bytes.hex()
    pub_hex = pub_bytes.hex()
    # 地址 = sha256(公钥) 前 40 位（仿以太坊格式，仅作标识）
    addr = "0x" + hashlib.sha256(pub_bytes).hexdigest()[:40]
    return {"private_key": priv_hex, "public_key": pub_hex, "address": addr}


def build_payload(sender: str, message: str, ts: str = None) -> str:
    """构造签名内容（统一格式）。"""
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    return f"{sender}|{message}|{ts}"


def sign(payload: str, priv_hex: str) -> str:
    """签名，返回 hex。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    sig = priv.sign(payload.encode("utf-8"))
    return sig.hex()


def verify(payload: str, sig_hex: str, pub_hex: str) -> bool:
    """验签。返回 True/False。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature  # noqa: F401
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(bytes.fromhex(sig_hex), payload.encode("utf-8"))
        return True
    except Exception:
        return False


def sign_message(sender: str, message: str, priv_hex: str) -> dict:
    """签一条消息，返回完整消息体（含签名）。"""
    ts = datetime.now(timezone.utc).isoformat()
    payload = build_payload(sender, message, ts)
    sig = sign(payload, priv_hex)
    return {"from": sender, "message": message, "ts": ts, "sig": sig}


def verify_message(msg: dict, pub_hex: str) -> bool:
    """验证一条消息。"""
    payload = build_payload(msg.get("from", ""), msg.get("message", ""),
                            msg.get("ts", ""))
    return verify(payload, msg.get("sig", ""), pub_hex)


if __name__ == "__main__":
    if not _ensure_crypto():
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "gen"

    if cmd == "gen":
        kp = gen_keypair()
        print("=== 新密钥对 ===")
        print(f"地址（公开）: {kp['address']}")
        print(f"公钥（公开）: {kp['public_key']}")
        print(f"私钥（保密）: {kp['private_key']}")
    elif cmd == "sign" and len(sys.argv) >= 4:
        print(sign(sys.argv[2], sys.argv[3]))
    elif cmd == "verify" and len(sys.argv) >= 5:
        ok = verify(sys.argv[2], sys.argv[3], sys.argv[4])
        print("✅ 验证通过" if ok else "❌ 签名不匹配（可能冒名）")
    elif cmd == "selftest":
        # 自测：生成→签名→验证→篡改检测
        kp = gen_keypair()
        payload = build_payload("MasterD(认知·三哥)", "你好", "2026-10-04T00:00:00")
        sig = sign(payload, kp["private_key"])
        assert verify(payload, sig, kp["public_key"]), "正常验签失败"
        assert not verify(payload + "X", sig, kp["public_key"]), "篡改应被检出"
        assert not verify(payload, sig, gen_keypair()["public_key"]), "错误密钥应失败"
        print("✅ selftest 通过（正常/篡改/错误密钥 三态正确）")
        print(f"   示例地址: {kp['address']}")
    else:
        print("用法: python3 agent_id.py {gen|sign|verify|selftest}")
