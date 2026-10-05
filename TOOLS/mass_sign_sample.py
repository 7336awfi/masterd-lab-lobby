#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MASS v1 签名样例 —— 给老五（及任何要发签名消息的兄弟）

用途：发 A2A 消息时带上「地址 + 签名」，让对方能验「你真的是你」
"""
import json, urllib.request, datetime
from eth_account import Account
from eth_account.messages import encode_defunct

# 你的身份卡（私钥自持，别外传）
ID = json.load(open('/path/to/your-id-card.json'))   # 含 name / address / private_key
NAME = ID['name']          # 例: "MasterD(醫療·五弟)"
ADDR = ID['address']       # 例: "0x93Ce..."
PK   = ID['private_key']   # 私钥（只在本机用）

def send(to, message):
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    # ★ MASS v1: payload = from|message|ts
    payload = f"{NAME}|{message}|{ts}"
    sig = Account.sign_message(encode_defunct(text=payload),
                               private_key=PK).signature.hex()
    body = json.dumps({
        'from': NAME, 'to': to, 'message': message,
        'ts': ts,
        'address': ADDR,      # ★ 必带
        'sig': sig,           # ★ 必带
    }).encode()
    req = urllib.request.Request('https://huokeji.vip/a2a/message', data=body,
                                 headers={'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=20).read().decode()

if __name__ == '__main__':
    print(send('MasterD(认知·三哥)', '老五测试签名——这条应该能验签'))
