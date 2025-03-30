#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基础智能体类，作为所有特定角色智能体的父类
"""

import uuid
import logging
import json # <--- 添加导入 json 模块
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone # 导入 timezone 用于 UTC

# 假设 MemorySystem 在这里可以被导入（或至少类型提示可用）
try:
    from utils.memory_system import MemorySystem
except ImportError:
    MemorySystem = type(None) # 使用 NoneType 进行类型提示

logger = logging.getLogger("Hospital-MultiAgent-System")

class BaseAgent:
    """基础智能体类，提供共通的功能"""

    def __init__(self, name: str, role: str, memory_system: Optional[MemorySystem] = None):
        """
        初始化基础智能体

        Args:
            name (str): 智能体名称.
            role (str): 智能体角色（例如 "doctor", "receptionist"）.
            memory_system (Optional[MemorySystem]): 记忆系统实例.

        Raises:
            ValueError: 如果 role 为空.
        """
        self.id = str(uuid.uuid4())
        self.name = name
        if not role: raise ValueError("Agent role cannot be empty")
        self.role = role
        self.memory_system = memory_system

        # 内部简单记忆（主要用于无 MemorySystem 时的备用）
        self._local_memory: Dict[str, Any] = {}
        self._conversation_history: List[Dict[str, Any]] = []

        logger.info(f"初始化 {self.role} 智能体: {name} (ID: {self.id})")

    def _now_utc_iso(self) -> str:
        """获取当前 UTC 时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat()

    def receive_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理接收到的消息，包含记录和错误处理。
        """
        # 记录接收到的消息
        self._record_conversation(direction="received", message=message)
        sender_info = f"{message.get('sender_role', '未知角色')} ({message.get('sender_id', 'N/A')})"
        # 尝试记录更简洁的消息内容摘要
        content_summary = str(message.get('content', {}))[:100] # 取前100个字符
        logger.debug(f"{self.role} {self.name} 收到来自 {sender_info} 的消息: {content_summary}...")

        # 具体处理逻辑由子类实现
        response = {} # 初始化默认响应
        try:
            response = self._process_message(message)
            # 确保 _process_message 返回的是字典
            if not isinstance(response, dict):
                 logger.error(f"{self.role} {self.name} 的 _process_message 返回了无效类型: {type(response)}. 将返回错误消息。")
                 raise TypeError("_process_message must return a dictionary.")

        except NotImplementedError:
             logger.error(f"子类 {self.__class__.__name__} 未实现 _process_message 方法！")
             sender_id = message.get("sender_id", "unknown")
             response = self.send_message(sender_id, {"status": "error", "message": f"{self.role} 未能处理请求：内部方法未实现。"})
        except Exception as e:
             logger.error(f"{self.role} {self.name} 在处理消息时发生严重错误: {e}", exc_info=True)
             sender_id = message.get("sender_id", "unknown")
             response = self.send_message(sender_id, {"status": "error", "message": f"处理您的请求时发生内部错误，请稍后重试。"})

        # 记录发送的响应
        # 确保 response 是我们期望的字典结构
        if response and "sender_id" in response: # 检查是否是 send_message 构建的结构
             self._record_conversation(direction="sent", message=response)
             receiver_info = response.get('receiver_id', '未知接收者')
             response_content_summary = str(response.get('content', {}))[:100]
             logger.debug(f"{self.role} {self.name} 发送响应给 {receiver_info}: {response_content_summary}...")
        else:
             logger.warning(f"{self.role} {self.name} 的 _process_message 未返回标准消息结构，响应内容: {response}")
             # 可以选择返回一个默认错误或尝试包装它，这里选择记录警告

        return response

    def _process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理消息的具体逻辑，【必须】被子类重写。

        Args:
            message: 接收到的消息对象，包含 'sender_id', 'sender_role', 'content' 等。

        Returns:
            响应消息字典，推荐使用 self.send_message() 构建。
            如果 Agent 需要结束当前流程或报告错误，应在 content 中包含明确的 'status' 字段。
        """
        raise NotImplementedError(f"子类 {self.__class__.__name__} 必须实现 _process_message 方法")

    def send_message(self, receiver_id: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        构造发送给其他智能体或Orchestrator的消息。

        Args:
            receiver_id: 接收者ID (例如 Orchestrator 的 ID 或另一个 Agent 的 ID)。
            content: 消息内容字典。应包含必要的处理结果、状态等信息。

        Returns:
            格式化的消息对象。
        """
        message = {
            "sender_id": self.id,
            "sender_name": self.name,
            "sender_role": self.role,
            "receiver_id": receiver_id,
            "content": content, # content 应该包含 status 等信息
            "timestamp_utc": self._now_utc_iso() # 使用 UTC 时间戳
        }
        return message

    def _record_conversation(self, direction: str, message: Dict[str, Any]) -> None:
        """
        记录对话历史到本地和 MemorySystem (如果可用)。
        """
        now_iso = self._now_utc_iso()
        # 尝试创建一个消息的浅拷贝用于本地历史，避免后续修改影响记录
        try:
             local_message_copy = message.copy()
        except:
             local_message_copy = message # 如果无法拷贝，使用原始引用

        entry = {
            "timestamp_utc": now_iso,
            "direction": direction,
            "message": local_message_copy
        }
        self._conversation_history.append(entry)

        # 如果有 MemorySystem，尝试记录到中央系统
        if self.memory_system and isinstance(self.memory_system, MemorySystem):
            patient_id: Optional[str] = None
            message_content = message.get("content", {}) if isinstance(message.get("content"), dict) else {}

            # --- 统一从 content 中提取 patient_id 和 context_id/consultation_id ---
            # Agent 在处理时应将这些 ID 放入 content 或 Agent 返回给 Orchestrator 的 content 中
            patient_id = message_content.get("patient_id")
            consultation_id = message_content.get("consultation_id") or message_content.get("context_id")

            # 如果 content 中没有，尝试从顶层消息获取 (作为后备)
            if not patient_id: patient_id = message.get("patient_id")
            if not consultation_id: consultation_id = message.get("consultation_id") or message.get("context_id")

            # 再次尝试从具体请求结构中获取 (最后的努力)
            if not patient_id:
                 potential_sources = ["reception_request", "diagnose_request", "prescription_request",
                                      "review_request", "patient_response", "followup_query", "general_query",
                                      "patient_query_about_prescription", "review_result", "diagnosis_result"]
                 for source_key in potential_sources:
                     source_data = message_content.get(source_key)
                     if isinstance(source_data, dict):
                         patient_id = source_data.get("patient_id")
                         if patient_id: break # 找到即停止

            # --- 确定角色和内容 ---
            conversation_role = ""
            log_content = {} # 存储更结构化的内容，而不是纯字符串
            metadata_to_save = {
                "direction": direction,
                "original_sender_id": message.get("sender_id"),
                "original_sender_role": message.get("sender_role"),
                "original_receiver_id": message.get("receiver_id"),
                "interaction_agent_id": None # 交互 Agent ID
            }
            if consultation_id: metadata_to_save['consultation_id'] = consultation_id

            if direction == "received":
                conversation_role = message.get("sender_role", "unknown_sender")
                metadata_to_save["interaction_agent_id"] = message.get("sender_id")
                log_content = message_content # 记录收到的内容
            elif direction == "sent":
                conversation_role = self.role
                metadata_to_save["interaction_agent_id"] = self.id
                log_content = message_content # 记录发送的内容

            # 如果成功获取 Patient ID，则记录
            if patient_id:
                try:
                    # --- 使用 json.dumps 将 log_content 转为字符串存储 ---
                    # 这是因为 MemorySystem 的 add_conversation_entry 当前接受字符串 content
                    # 如果未来 MemorySystem 支持存储字典，可以移除 dumps
                    log_content_str = json.dumps(log_content, ensure_ascii=False, default=str)
                    # ----------------------------------------------------

                    self.memory_system.add_conversation_entry(
                        patient_id=patient_id,
                        role=conversation_role,
                        content=log_content_str, # 传递 JSON 字符串
                        metadata=metadata_to_save
                    )
                except AttributeError:
                     logger.error(f"MemorySystem 实例 ({type(self.memory_system)}) 似乎没有 add_conversation_entry 方法或实例无效。")
                except Exception as e:
                    logger.error(f"记录对话到 MemorySystem 时出错 (Patient: {patient_id}): {e}", exc_info=True)
            else:
                 # 仅当 direction 是 received 且我们是处理者时，记录无法关联患者的警告可能更有用
                 if direction == "received":
                      logger.warning(f"无法从消息中提取 patient_id 以记录对话历史: Keys={list(message_content.keys())}")


    # --- Memory Interaction Wrappers (简化) ---

    def update_memory(self, key: str, value: Any):
        """(简化) 更新智能体的本地记忆。与中央 MemorySystem 的交互应通过其自身方法完成。"""
        logger.debug(f"{self.role} {self.name} 更新本地记忆: {key}={str(value)[:50]}...")
        self._local_memory[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        """(简化) 获取智能体的本地记忆。"""
        return self._local_memory.get(key, default)

    def get_conversation_history(self, patient_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取对话历史。优先从 MemorySystem 获取指定患者的历史，否则返回本地历史。
        """
        if patient_id and self.memory_system and isinstance(self.memory_system, MemorySystem):
            try:
                 # 获取全部历史（或按需筛选角色）
                 return self.memory_system.get_conversation_history(patient_id, limit=limit)
            except AttributeError:
                 logger.error(f"MemorySystem 实例 ({type(self.memory_system)}) 似乎没有 get_conversation_history 方法或实例无效。")
                 return self._conversation_history[-limit:] # Fallback to local
            except Exception as e:
                logger.error(f"从 MemorySystem 获取对话历史时出错 (Patient: {patient_id}): {e}")
                return self._conversation_history[-limit:] # Fallback to local

        # 返回本地历史的最近 N 条
        return self._conversation_history[-limit:]

# ... (文件结束)