# 身份验证器 · 技术方案 v4（对齐 A2A 官方标准）

> 出：MasterD(认知·三哥)
> 日期：2026-10-04
> 性质：技术方案（v3 + A2A 官方标准对齐）
> 范围：只谈技术+认知
> 来源：A2A Protocol Specification v1.0.0（a2a-protocol.org）

---

## 〇、v4 核心突破

**之前我们在「自己设计身份证」。v4 发现：行业标准 A2A 就是干这个的。**

> **A2A 官方定义：「Agent Card: A JSON metadata document … describing its identity, capabilities, skills, service endpoint, and authentication requirements.」**
> **→ 「智能体身份证」的官方名字 = Agent Card。**

**结论：直接对齐 A2A，不自己造。**

---

## 一、A2A 官方规范要点（原文摘录）

### 1.1 身份：Agent Card
```
· 发布在 well-known URL（RFC 8615）
· 任何客户端可匿名 GET 发现
· 含：identity / capabilities / skills / service endpoint / auth requirements
```

### 1.2 防篡改：AgentCardSignature ★关键
```
官方原话：
「The A2A spec defines AgentCardSignature for exactly this:
 a JSON Web Signature (RFC 7515) computed over a canonicalized form
 of the card (JSON Canonicalization Scheme, RFC 8785)
 so signatures are stable across serializers.」

→ 做法：对 Agent Card 做 JWS 签名 + JSON 规范化
→ 为什么：Agent Card 本身是攻击面（可被改写→劫持/注入）
```
**★ 这一条，解决了我们「自证陷阱」「登记表防篡改」的洞。**

### 1.3 认证：复用现有标准
```
官方原话：
「Rather than defining a new identity system,
 it aligns with OpenAPI authentication schemes
 (OAuth 2.0, OpenID Connect, API keys, mutual TLS)」

→ securitySchemes（声明支持哪些）
→ security（声明需要哪个）
```

### 1.4 长任务 + 人类介入：内置
```
「Async First: Designed for long-running tasks and human-in-the-loop interactions.」
「Asynchronicity: Natively support long-running tasks / human-in-the-loop.」
```

### 1.5 不透明执行：设计原则
```
「Opaque Execution: Agents collaborate based on declared capabilities
 and exchanged information, without needing to share their internal thoughts,
 plans, or tool implementations.」
→ 保护内部（思想/计划/工具实现不共享）
```

### 1.6 三层结构
```
Layer 1: 数据模型（Task / Message / AgentCard / Part / Artifact）
Layer 2: 操作（Send Message / Get Task / Cancel Task / Get Agent Card）
Layer 3: 协议绑定（JSON-RPC / gRPC / HTTP-REST）
```

---

## 二、v4 架构（对齐 A2A）

```
【我们原来的自建】            【v4 对齐 A2A】
智能体身份证              →  Agent Card（well-known URL）
地址 + 签名              →  AgentCardSignature（JWS + JSON规范化）
公钥表                   →  securitySchemes（OAuth2/OIDC/mTLS）
协议                    →  A2A 三层（数据模型/操作/绑定）
长任务                   →  Async First（内置）
人类批准                 →  Human-in-the-loop（内置）
```

---

## 三、映射表（我们的 → A2A 的）

| 我们的概念 | A2A 对应 |
|---|---|
| 身份证（地址+方向） | **Agent Card**（identity/description/skills） |
| 签名 | **AgentCardSignature**（JWS over canonicalized JSON） |
| 公钥表 | **securitySchemes** |
| 消息 | **Message**（role + Parts） |
| 任务 | **Task**（stateful, 生命周期） |
| 端点 | **supportedInterfaces / service endpoint** |
| 能力 | **capabilities（flags）** |
| 技能 | **skills** |

---

## 四、落地步骤（对齐 A2A）

```
第1步：把「我们的名片」改成「A2A Agent Card 格式」
        · 放 well-known URL
        · 含 identity/skills/capabilities/securitySchemes
第2步：加 AgentCardSignature
        · 对 Agent Card 做 JWS 签名
        · 用 RFC 8785（JSON 规范化）保证签名稳定
第3步：认证对接
        · securitySchemes 声明 OAuth2/OIDC/mTLS
        · 不自己发明认证语义
第4步：协议对接
        · 实现 A2A 操作（Send Message / Get Task / Cancel Task）
        · 用 JSON-RPC 或 HTTP-REST 绑定
```

---

## 五、参考实现

| 用途 | 参考 |
|---|---|
| **A2A 规范** | `a2a-protocol.org/latest/specification/` |
| **A2A SDK** | `a2aproject/A2A`（github） |
| **Agent Card 签名** | JWS（RFC 7515）+ JSON Canonicalization（RFC 8785） |
| **认证** | OAuth 2.0 / OIDC / mTLS |
| **审计** | OpenTelemetry GenAI semantic conventions |
| **策略** | OPA（Open Policy Agent）+ Rego |

---

## 六、修正记录（v3 → v4）

| # | v3 | v4 |
|---|---|---|
| 1 | 自己设计身份证 | **用 A2A 的 Agent Card** |
| 2 | 自己设计签名 | **用 AgentCardSignature（JWS+JCS）** |
| 3 | 公钥表 | **securitySchemes（复用 OAuth/OIDC）** |
| 4 | 长任务"要自己设计" | **A2A Async First（内置）** |
| 5 | 人类批准"要自己设计" | **A2A human-in-the-loop（内置）** |
| 6 | 协议"要自己设计" | **A2A 三层（标准）** |

---

## 七、仍保留的「我们自己的」（不可替代）

**A2A 是「协议层」，但我们的「策略层」是自己的：**

```
· 约束维度（amount/target/action/时间/次数/频率）
· 审核门（四关审核）
· 记忆防污染
· 状态稳定（防漂移）
· 认知提纯
→ 这些是 A2A 不覆盖的，是我们的核心
```

**→ DeepSeek 的话：「别重造协议，重造的是你的策略层。」**

---

## 八、核心认知（v4 总结）

```
1. 智能体身份证 = A2A 的 Agent Card（行业标准，不自己造）
2. 防篡改 = AgentCardSignature（JWS + JSON规范化）
3. 认证 = 复用 OAuth2/OIDC（不发明新身份系统）
4. 长任务/人类介入 = A2A 内置（Async First / HITL）
5. 不透明执行 = A2A 设计原则（保护内部）
6. 我们自己的 = 策略层（约束/审核/记忆/认知）
7. 对齐 A2A = 能和「外面的智能体」互通（不止五兄弟）
```

---

## 九、⚠️ 诚实标注

```
· 本方案为「对齐建议」，落地需实测（A2A SDK 是否易用）
· A2A 是 Google 主导标准，与我们的自建协议有差异
  → 迁移要评估成本
· 「意图可验证」仍不可判定（A2A 也不解决）
· 天花板仍在（prompt injection）
```

---

_MasterD(认知·三哥) · 2026-10-04_
**（v4：对齐 A2A 官方标准）**
