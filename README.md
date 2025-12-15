# Auto Accept Requests 插件(适配dev分支)(核心API仍未适配,占时不可用(已发起PR占位通过))

自动同意 Napcat/OneBot 的群邀请、加群申请与好友申请，支持白名单控制、关键词匹配与自动回复通知。

## 功能特性

- **群邀请自动处理**：自动同意好友或指定名单发起的群邀请。
- **好友申请自动处理**：自动同意好友申请。
- **加群申请自动处理**：
  - 支持按群号区分不同的验证问题/答案索引。
  - 支持关键词模糊匹配（包含关键词即自动同意）。
  - 支持单条配置多个关键词（用逗号分隔）。
  - 支持跳过验证直接同意所有申请。
  - 支持自动拒绝未匹配答案的申请。
  - 支持未处理申请通知管理员（私聊）。
- **通知反馈**：可选在同意后私聊通知发起人，或在需人工介入时通知管理员。

## 安装

将插件文件夹放入 `MoFox-Core/plugins/` 目录下：

```
MoFox-Core/
├── plugins/
│   ├── auto_accept_requests/  <-- 插件目录
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── ...
```

## 配置说明

配置文件位于 `config/plugins/auto_accept_requests/config.toml`，首次运行后自动生成。

### 基础配置

```toml
[plugin]
enabled = true              # 插件总开关
config_version = "1.0.0"    # 配置文件版本
```

### 功能配置详解

```toml
[features]
# --- 群邀请 (被邀请入群) ---
enable_auto_accept_group_invite = true
# 允许自动同意的邀请发起人白名单，为空则默认仅允许好友
# 格式：[["qq", "123456"]] 或 [{qq="123456"}]
auto_accept_group_invite_initiators = []

# --- 好友申请 ---
enable_auto_accept_friend_request = false

# --- 加群申请 (他人申请入群) ---
# 是否开启加群申请自动处理
enable_auto_handle_group_add_request = true

# 是否跳过答案验证直接同意（慎用，优先级最高）
# 开启后将忽略关键词匹配逻辑，直接同意所有申请
enable_skip_answer_verification = false

# 群号与答案索引映射
# 格式：[["qq", "群号", "索引ID"]]
# 示例：群 12345 使用索引 "1"，群 67890 使用索引 "2"
group_answer_indices = [
    ["qq", "12345", "1"],
    ["qq", "67890", "2"]
]

# 答案关键词配置
# 格式：[["qq", "关键词", "索引ID"]]
# 支持单条配置多个关键词（用逗号分隔）
# 示例：索引 "1" 对应的答案包含 "暗号A" 或 "暗号B"
answer_keywords = [
    ["qq", "暗号A,暗号B", "1"],
    ["qq", "暗号C", "2"]
]

# 是否自动拒绝未匹配答案的申请
# 如果设为 true，答案错误的申请会被直接拒绝，不会通知管理员
enable_auto_reject_group_add_unmatched = false

# --- 通知配置 ---

# 加群申请人工处理通知开关
# 当申请未被自动同意且未被自动拒绝时，通知管理员
enable_group_add_request_notify = true

# 管理员列表
# 格式：[["qq", "管理员QQ"]]
group_add_request_notify_admins = [["qq", "123456789"]]

# 通知消息模板
# 可用变量：{group_id} 群号, {user_id} 用户QQ, {comment} 验证消息
group_add_request_notify_message = "收到加群申请，因未匹配回答关键词，请及时处理！！！\n群：{group_id}\n用户：{user_id}\n答案：{comment}"

# 同意群邀请后通知发起人
enable_notify_accept_group_invite = true
notify_accept_group_invite_message = "已自动同意你的群邀请"

# 同意好友申请后通知发起人
enable_notify_accept_friend_request = false
notify_accept_friend_request_message = "已通过你的好友申请，打个招呼吧"
```

## 逻辑流程图

### 加群申请处理流程

1. **收到加群请求** (`request_type=group`, `sub_type=add`)
2. **检查 `enable_skip_answer_verification`**
   - `True` -> **直接同意** (流程结束)
   - `False` -> 进入下一步
3. **关键词匹配**
   - 根据 `group_answer_indices` 找到当前群对应的 `索引ID`
   - 根据 `answer_keywords` 找到对应的关键词列表
   - 检查用户回答 (`comment`) 是否包含任一关键词
   - **包含** -> **自动同意** (流程结束)
   - **不包含** -> 进入下一步
4. **检查 `enable_auto_reject_group_add_unmatched`**
   - `True` -> **自动拒绝** (流程结束)
   - `False` -> 进入下一步
5. **检查 `enable_group_add_request_notify`**
   - `True` -> **通知管理员** (等待人工处理)
   - `False` -> 忽略 (无操作)

## 常见问题

Q: 为什么配置了关键词还是不通过？
A: 请检查 `group_answer_indices` 中的群号是否正确（注意是字符串类型），以及 `answer_keywords` 中的索引ID是否与群设置的一致。

Q: 管理员收不到通知？
A: 请确认 Bot 是否与管理员是好友关系（非必须，但部分情况下非好友无法发送临时会话），以及 `group_add_request_notify_admins` 格式是否正确。