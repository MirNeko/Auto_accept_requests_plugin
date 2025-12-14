"""
Auto Accept Requests 插件

功能：
- 自动同意 Napcat/OneBot 的群邀请与好友申请（通过 ON_NOTICE_RECEIVED 事件）
- 支持按发起人 QQ 白名单判断是否自动同意
- 可选通知邀请/申请发起人（私聊提示）
"""
from __future__ import annotations

from typing import Any, ClassVar

from src.plugin_system import (
    BaseEventHandler,
    BasePlugin,
    ConfigField,
    EventType,
    register_plugin,
)
from src.plugin_system.base.base_event import HandlerResult
from src.plugin_system.apis import config_api, send_api
from src.common.logger import get_logger

logger = get_logger("auto_accept_requests")


class AutoAcceptRequestHandler(BaseEventHandler):
    """基于 Notice 事件的自动同意请求处理器"""

    handler_name = "auto_accept_requests_handler"
    handler_description = "自动同意群邀请与好友申请"
    weight = 10
    intercept_message = False
    init_subscribe: ClassVar[list[EventType | str]] = [EventType.ON_NOTICE_RECEIVED]

    async def execute(self, kwargs: dict | None) -> HandlerResult:
        try:
            if not kwargs:
                return HandlerResult(True, True, "empty kwargs", self.handler_name)

            message = kwargs.get("message")
            notice_type = kwargs.get("notice_type") or ""
            chat_stream = kwargs.get("chat_stream")

            if not chat_stream:
                return HandlerResult(True, True, "missing chat_stream", self.handler_name)

            # 兼容 DatabaseMessages 模型对象
            inviter_id = ""
            request_detail = {}
            try:
                # DatabaseMessages
                inviter_id = getattr(getattr(message, "user_info", None), "user_id", "") or ""
                additional_cfg = getattr(message, "additional_config", None)
                if isinstance(additional_cfg, dict):
                    request_detail = additional_cfg.get("request_detail", {}) or {}
                elif isinstance(additional_cfg, str) and additional_cfg:
                    import json as _json
                    try:
                        parsed = _json.loads(additional_cfg)
                        if isinstance(parsed, dict):
                            request_detail = parsed.get("request_detail", {}) or {}
                    except Exception:
                        pass
            except Exception:
                inviter_id = inviter_id or ""

            # 兜底：适配 envelope 字典路径（理论上不会触发）
            if not inviter_id and isinstance(message, dict):
                inviter_id = str(message.get("message_info", {}).get("user_info", {}).get("user_id", ""))
                request_detail = message.get("message_info", {}).get("additional_config", {}).get("request_detail", {}) or {}

            # 好友请求
            if notice_type == "friend_request":
                if not self._cfg("features.enable_auto_accept_friend_request", False):
                    return HandlerResult(True, True, "friend auto accept disabled", self.handler_name)
                flag = request_detail.get("flag")
                await self._accept_friend_request(chat_stream.stream_id, flag, inviter_id)
                return HandlerResult(True, True, "friend accepted", self.handler_name)

            # 群邀请 / 加群申请
            if notice_type == "group_invite":
                flag = request_detail.get("flag")
                sub_type = request_detail.get("sub_type", "invite")

                # 加群申请 (sub_type='add')
                if sub_type == "add":
                    return await self._handle_group_add_request(chat_stream.stream_id, request_detail, inviter_id)

                # 群邀请 (sub_type='invite')
                if not self._cfg("features.enable_auto_accept_group_invite", False):
                    return HandlerResult(True, True, "group auto accept disabled", self.handler_name)
                
                if not await self._should_accept_group(inviter_id, chat_stream.stream_id):
                    return HandlerResult(True, True, "group inviter not allowed", self.handler_name)
                await self._accept_group_invite(chat_stream.stream_id, flag, sub_type, inviter_id)
                return HandlerResult(True, True, "group accepted", self.handler_name)

            return HandlerResult(True, True, "skipped", self.handler_name)
        except Exception as e:
            logger.error(f"[AutoAccept] 执行失败: {e}")
            return HandlerResult(False, True, str(e), self.handler_name)

    async def _handle_group_add_request(self, stream_id: str, request_detail: dict, user_id: str) -> HandlerResult:
        """处理加群申请"""
        if not self._cfg("features.enable_auto_handle_group_add_request", False):
            return HandlerResult(True, True, "group add request handling disabled", self.handler_name)

        comment = request_detail.get("comment", "")
        flag = request_detail.get("flag")
        group_id = str(request_detail.get("group_id", ""))

        # 0. 检查是否跳过验证直接同意
        if self._cfg("features.enable_skip_answer_verification", False):
            await self._accept_group_request(stream_id, flag, "add", user_id, approve=True)
            return HandlerResult(True, True, "group add accepted (skip verification)", self.handler_name)

        # 获取配置
        group_indices_config = self._cfg("features.group_answer_indices", [])
        answer_keywords_config = self._cfg("features.answer_keywords", [])

        # 1. 查找当前群对应的答案索引
        target_indices = set()
        for item in group_indices_config:
            # item format: ["qq", "group_id", "index"]
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                # 简单适配：忽略平台检查或只检查 "qq"
                if str(item[1]) == group_id:
                    target_indices.add(str(item[2]))

        # 2. 如果该群没有配置任何规则，直接跳过自动处理（或视为不匹配？）
        # 根据需求：没有配置规则的群，应该不自动同意，进而进入未匹配流程
        
        is_matched = False
        if target_indices:
            # 3. 查找这些索引对应的关键词
            allowed_keywords = set()
            for item in answer_keywords_config:
                # item format: ["qq", "keywords", "index"]
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    keywords_str = str(item[1])
                    index = str(item[2])
                    if index in target_indices and keywords_str:
                        # 支持逗号分隔多个关键词
                        for kw in keywords_str.replace("，", ",").split(","):
                            clean_kw = kw.strip()
                            if clean_kw:
                                allowed_keywords.add(clean_kw)
            
            # 4. 检查匹配（包含关系）
            for kw in allowed_keywords:
                if kw in comment:
                    is_matched = True
                    break

        if is_matched:
            await self._accept_group_request(stream_id, flag, "add", user_id, approve=True)
            return HandlerResult(True, True, "group add accepted", self.handler_name)

        # 5. 未匹配处理
        if self._cfg("features.enable_auto_reject_group_add_unmatched", False):
            await self._accept_group_request(stream_id, flag, "add", user_id, approve=False, reason="答案不正确")
            return HandlerResult(True, True, "group add rejected (unmatched)", self.handler_name)

        # 6. 通知管理员
        if self._cfg("features.enable_group_add_request_notify", True):
            admins = self._cfg("features.group_add_request_notify_admins", [])
            if admins:
                msg_tmpl = self._cfg("features.group_add_request_notify_message", "收到加群申请...")
                msg = msg_tmpl.replace("{group_id}", str(group_id)).replace("{user_id}", str(user_id)).replace("{comment}", comment)
                
                notified_count = 0
                for admin in admins:
                    target_id = ""
                    if isinstance(admin, dict):
                        target_id = str(admin.get("qq", ""))
                    elif isinstance(admin, (list, tuple)) and len(admin) >= 2 and str(admin[0]).lower() == "qq":
                        target_id = str(admin[1])
                    
                    if target_id:
                        try:
                            await send_api.adapter_command_to_stream("send_private_msg", {"user_id": int(target_id), "message": msg}, stream_id=stream_id)
                            notified_count += 1
                        except Exception:
                            pass
                
                if notified_count > 0:
                    return HandlerResult(True, True, f"group add notified {notified_count} admins", self.handler_name)

        return HandlerResult(True, True, "group add ignored", self.handler_name)

    async def _accept_group_request(self, stream_id: str, flag: Any, sub_type: str, user_id: str, approve: bool = True, reason: str = "") -> None:
        params = {"flag": flag, "sub_type": sub_type, "approve": approve, "reason": reason}
        resp = await send_api.adapter_command_to_stream("set_group_add_request", params, stream_id=stream_id)
        action = "同意" if approve else "拒绝"
        logger.info(f"[AutoAccept] 群请求{action}: user={user_id}, napcat返回={resp!s}")



    def _cfg(self, key: str, default: Any = None) -> Any:
        return config_api.get_plugin_config(getattr(self, "plugin_config", {}) or {}, key, default)

    async def _should_accept_group(self, inviter_id: str, stream_id: str) -> bool:
        allow_list = self._cfg("features.auto_accept_group_invite_initiators", []) or []
        if not allow_list:
            # 未配置白名单：查询好友列表，仅同意“好友”发起
            try:
                resp = await send_api.adapter_command_to_stream("get_friend_list", {}, stream_id=stream_id, timeout=30.0)
                if resp and resp.get("status") == "ok":
                    data = resp.get("data", []) or []
                    friend_ids = {str(x.get("user_id")) for x in data if isinstance(x, dict)}
                    return inviter_id in friend_ids
            except Exception:
                pass
            return False
        for item in allow_list:
            if isinstance(item, dict) and str(item.get("qq", "")) == inviter_id:
                return True
            if isinstance(item, (list, tuple)) and len(item) >= 2 and str(item[0]).lower() == "qq" and str(item[1]) == inviter_id:
                return True
        return False

    async def _accept_group_invite(self, stream_id: str, flag: Any, sub_type: str, inviter_id: str) -> None:
        params = {"flag": flag, "sub_type": sub_type, "approve": True, "reason": ""}
        resp = await send_api.adapter_command_to_stream("set_group_add_request", params, stream_id=stream_id)
        logger.info(f"[AutoAccept] 群邀请同意: inviter={inviter_id}, napcat返回={resp!s}")
        if self._cfg("features.enable_notify_accept_group_invite", False):
            msg = self._cfg("features.notify_accept_group_invite_message", "已自动同意你的群邀请")
            try:
                from src.chat.message_receive.chat_stream import get_chat_manager
                chat = await get_chat_manager().get_stream(stream_id)
                if chat and chat.group_info and chat.group_info.group_id:
                    msg = msg.replace("{group_id}", str(chat.group_info.group_id))
            except Exception:
                pass
            await send_api.adapter_command_to_stream("send_private_msg", {"user_id": int(inviter_id), "message": msg}, stream_id=stream_id)

    async def _accept_friend_request(self, stream_id: str, flag: Any, requester_id: str) -> None:
        params = {"flag": flag, "approve": True, "remark": ""}
        resp = await send_api.adapter_command_to_stream("set_friend_add_request", params, stream_id=stream_id)
        logger.info(f"[AutoAccept] 好友请求同意: requester={requester_id}, napcat返回={resp!s}")
        if self._cfg("features.enable_notify_accept_friend_request", False):
            msg = self._cfg("features.notify_accept_friend_request_message", "已通过你的好友申请，打个招呼吧")
            await send_api.adapter_command_to_stream("send_private_msg", {"user_id": int(requester_id), "message": msg}, stream_id=stream_id)


@register_plugin
class AutoAcceptRequestsPlugin(BasePlugin):
    """自动同意请求插件"""

    plugin_name = "auto_accept_requests_pulgin"
    enable_plugin = True
    plugin_priority = 30
    config_file_name = "config.toml"

    config_section_descriptions: ClassVar = {
        "plugin": "插件开关",
        "features": "自动同意与通知配置",
    }

    config_schema: ClassVar[dict] = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用自动同意请求插件"),
            "config_version": ConfigField(type=str, default="1.0.0", description="配置文件版本"),
        },
        "features": {
            # ---------- 好友申请相关配置 -----------------
            "enable_auto_accept_friend_request": ConfigField(type=bool, default=False, description="是否自动同意好友请求"),
            "enable_notify_accept_friend_request": ConfigField(type=bool, default=False, description="是否通知好友申请人"),
            "notify_accept_friend_request_message": ConfigField(type=str, default="已通过你的好友申请，打个招呼吧", description="好友申请通知模板"),

            # ---------- 好友邀请加群申请相关配置 -----------------
            "enable_auto_accept_group_invite": ConfigField(type=bool, default=False, description="是否自动同意群邀请"),
            "auto_accept_group_invite_initiators": ConfigField(type=list, default=[], description="允许自动同意的群邀请发起人，支持 [{qq='123'}] 或 [[\"qq\",\"123\"]]",),
            "enable_notify_accept_group_invite": ConfigField(type=bool, default=True, description="是否通知群邀请发起人"),
            "notify_accept_group_invite_message": ConfigField(type=str, default="已自动同意你的群邀请", description="群邀请通知模板"),

            # ---------- 加群申请相关配置 -----------------
            "enable_auto_handle_group_add_request": ConfigField(type=bool, default=False, description="是否自动处理加群申请"),
            "group_answer_indices": ConfigField(type=list,default=[],description="群聊与答案索引的映射，格式：[[\"qq\", \"群号\", \"索引值\"]]"),
            "answer_keywords": ConfigField(type=list, default=[], description="答案索引与关键词的映射，格式：[[\"qq\", \"关键词\", \"索引值\"]]"),
            "enable_skip_answer_verification": ConfigField(type=bool, default=False, description="是否跳过答案验证直接自动同意加群申请(优先级：高)"),
            "enable_group_add_request_notify": ConfigField(type=bool, default=True, description="是否通知管理员需人工处理的加群申请(优先级：中)"),
            "group_add_request_notify_admins": ConfigField(type=list, default=[], description="加群申请需人工处理时通知的管理员列表，支持 [{qq='123'}] 或 [[\"qq\",\"123\"]]"),
            "group_add_request_notify_message": ConfigField(type=str, default="收到加群申请,因未匹配回答关键词,请及时处理！！！", description="通知管理员的消息模板"),

            "enable_auto_reject_group_add_unmatched": ConfigField(type=bool, default=False, description="是否自动拒绝未匹配回答的申请(优先级：低)"),

        },
    }

    def get_plugin_components(self) -> list:
        """注册事件处理器组件"""
        return [(AutoAcceptRequestHandler.get_handler_info(), AutoAcceptRequestHandler)]
