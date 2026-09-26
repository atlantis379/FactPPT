# 离线溯源验证（第三方可自行执行）

本目录下的脚本**只依赖 Python 标准库**，不需要安装本项目的应用、skill 或任何第三方包。
目的：让"我们的审计日志没有被改过"这句话，从"请相信我们的数据库"变成**你可以自己算一遍**。

## 1. 验证审计链

拿到导出的项目 JSON（应用持久化文件 `data/projects.json`，或其副本）后：

```bash
python tools/provenance.py verify-chain <exported_projects.json>
```

退出码 `0` = 全部项目的链完整；`1` = 至少一个项目失败。输出示例：

```json
{
  "ok": false,
  "failed": 1,
  "targets": [
    {"target": "prj_c9126906", "ok": false, "code": "ENTRY_HASH_MISMATCH",
     "first_bad_index": 0, "reason": "entry 0 failed: ENTRY_HASH_MISMATCH"}
  ]
}
```

`code` 是稳定的机器可读值：`OK` / `EMPTY` / `SEQ_MISMATCH` / `PREV_MISMATCH` /
`ENTRY_HASH_MISMATCH` / `PAYLOAD_MISMATCH` / `MALFORMED_ENTRY` / `UNSUPPORTED_VERSION`。

打印当前链头（S1 的锚要锚定这个值）：

```bash
python tools/provenance.py head <exported_projects.json>
```

## 2. 验证外部锚（关闭"尾部截断"缺口）

链只能证明自洽，**证明不了完整**：删掉末尾若干条会留下一条更短但依然自洽的链。
把链头发布到链之外的锚文件，就能让"变短的链"对不上已发布的链头。

```bash
# 生成签名密钥（一次性）
python tools/anchor.py keygen --out keys

# 发布锚（读取项目 JSON，可为每个项目追加一条锚）
python tools/anchor.py append <anchors.jsonl> <projects.json> --key keys/anchor-ed25519.pem --note "交付 v1"

# 第三方验证：锚文件自身 + 每个项目的链 + 项目与锚的一致性 + 签名
python tools/anchor.py verify <anchors.jsonl> <projects.json> --pubkey keys/anchor-ed25519.pub.pem
```

`verify` 退出码 `0` = 全部通过。结果码：

| 码 | 含义 |
|---|---|
| `CHAIN_TRUNCATED_BELOW_ANCHOR` | **链比锚短** —— 有条目被删除（S0 抓不到，这里抓到） |
| `CHAIN_HEAD_MISMATCH` | 长度没变，但锚定位置的哈希变了（尾部被**一致地**重写） |
| `NO_ANCHOR_FOR_PROJECT` | 该项目从未锚定，**不按通过处理** |
| `ANCHOR_HASH_MISMATCH` / `ANCHOR_LINK_MISMATCH` / `ANCHOR_SEQ_MISMATCH` | 锚文件自身被改/被删/被换序 |
| `ANCHOR_BACKDATED` | 锚的时间早于前一条（只追加文件不允许回溯） |
| `SIGNATURE_OK` / `SIGNATURE_INVALID` / `SIGNATURE_LIB_MISSING` / `SIGNATURE_KEY_MISSING` | 签名结论；**库缺失时报 `LIB_MISSING`，绝不报通过** |

锚文件是 **JSONL 只追加**，每条锚链接前一条，所以"只追加"是**密码学强制的**，不是约定：
改写或删除任一历史锚都会断链。对已损坏的锚文件**拒绝继续追加**（避免把证据埋掉）。

### 未实现：RFC 3161 外部时间戳

计划中的 `--tsa <url>` **没有实现**，原因是本环境把所有 TSA 主机名解析到
`198.18.0.0/15`（DNS 拦截保留段），**无法真实验证时间戳令牌**。与其交付一条
未经任何验证的网络密码学路径（那正是本项目要消除的"声称了但没验证"），不如留出
明确接缝：锚记录里保留 `tsa` 字段位置，待 S1.1 在可验证网络下补齐。

## 3. 验证交付物文件哈希

```bash
python tools/provenance.py verify-files <bundle_dir> <delivery_manifest.json> \
    --pptx deck.pptx --deck semantic_deck.json
```

清单里只存了摘要、没存路径的条目会报 `UNVERIFIABLE_NO_PATH`，**不会被当作"已验证"**。

## 4. 链的构型

```text
entry_hash = SHA256(domain || canonical({version, seq, at, action,
                                         payload_sha256, prev_hash}))
```

`seq` / `at` / `action` 都参与哈希，因此**改时间、改标签、换顺序**同样可检测，不只是改内容。

## 5. 这套机制能证明什么、不能证明什么

能检测：

| 攻击 | 检测结果 |
|---|---|
| 修改某条 payload 内容 | `PAYLOAD_MISMATCH` 或 `ENTRY_HASH_MISMATCH` |
| 删除中间某条 | `SEQ_MISMATCH` / `PREV_MISMATCH` |
| 交换两条顺序 | `SEQ_MISMATCH` |
| 改写动作标签或时间 | `ENTRY_HASH_MISMATCH` |
| 直接伪造 `entry_hash` | `ENTRY_HASH_MISMATCH` |
| 塞入未上链的旧格式条目 | `MALFORMED_ENTRY` |

**不能检测（须靠外部锚，见第 2 节）**：

- **尾部截断**。删掉末尾若干条会留下一条更短但完全自洽的链。把整条链清空会被判 `EMPTY`
  （不是"通过"），但"删到只剩前 k 条"仅凭链**仍会报 `OK`**。
  一旦该项目发布过锚，`tools/anchor.py verify` 会报 `CHAIN_TRUNCATED_BELOW_ANCHOR`。
  因此：**未锚定的项目，其完整性无法对抗截断**。
- 链与锚都**不能**证明记录的内容在业务上正确，只能证明它自记录以来未被改动。

## 6. 历史数据的诚实标注

对在本机制上线之前就已存在的日志，应用的迁移逻辑会补建链，并把该项目标记为
`chain_provenance.status = "MIGRATED"`，附注：

> Chain established at migration time. Earlier audit_log entries carry no
> cryptographic standing: this chain fixes the state from migration onward, it
> does not attest the past.

**这是刻意的**：补建的链只能固定"从现在起"的状态，不能追溯担保过去。把它说成"一直可审计"
就是本项目要消除的那类自证。
