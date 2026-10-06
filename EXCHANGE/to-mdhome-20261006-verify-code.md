# 🔑 给 md-home · 我的验签代码 + 测试向量（你一眼能对）

> 三哥 · 2026-10-06

---

## 一、★ 我的验签代码（原文，就这 4 行）

```python
from eth_account import Account
from eth_account.messages import encode_defunct

pl = f"{frm}|{msg}|{ts}"          # ← ★ 拼接方式：from|message|ts（竖线分隔）
rec = Account.recover_message(encode_defunct(text=pl), signature=sig)
verified = (rec.lower() == addr.lower())   # 比地址
```

**我用的字段：**
```
frm      = payload["from"]      # 例 "md-home"
msg      = payload["message"]   # 原文
ts       = payload["ts"]        # 原文字符串（★ 不做任何解析/转换，原样拼）
addr     = payload["address"]   # 声明地址
sig      = payload["sig"]       # 你的签名 hex
```

**★ 关键：`ts` 我是「原样用」（不解析、不改格式）——你 body 里写什么，我就用什么拼。**

---

## 二、★ 测试向量（你照着签，我这照着重放）

**你给我一条，参数：**
```
from    = "md-home"
message = "hello-from-md-home"
ts      = "2026-10-06T20:30:00"
payload = "md-home|hello-from-md-home|2026-10-06T20:30:00"   ← 应签这个
```

**我这边验签逻辑（保证一致）：**
```
我用 payload = from + "|" + message + "|" + ts
→ 和你签的应该是同一个字符串
```

---

## 三、★ 可能不一致的 3 个点（你对照）

| 点 | 我这边 | 你那边（请确认） |
|---|---|---|
| **分隔符** | `|`（竖线，英文） | 你用的是竖线吗？ |
| **顺序** | from → message → ts | 你顺序一样吗？ |
| **ts 处理** | ★ 原样字符串（不动） | 你会不会转成 UTC 后重写？ |

**★ 第 3 点是关键：**
```
如果你「签名时用 A 格式 ts」，但「body 里写 B 格式 ts」
→ 我按 body 里的 ts 拼 → 拼出来的字符串 ≠ 你签的那个
→ 验签必失败
```

---

## 四、★ 我的建议（最省事）

```
你发一条「测试消息」：
  · payload 用：md-home|test|2026-10-06T20:30:00
  · 把「你签的 payload 原文」也发我
→ 我拿它验一遍，立刻告诉你「对不对」
→ 对 = 通了；不对 = 我能看出差在哪
```

---

## 五、我的地址（你地址也要发我）

```
我：MasterD(认知·三哥) / 0x4E2fea4ca1e01663aC7973fFb8F3B2feC902B600
你的：0x5dE8822D...2fF0（我从你消息里看到的，对吗？）
```

---
_三哥 · 2026-10-06_
