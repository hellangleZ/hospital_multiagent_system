# utils/memory_system.py

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
记忆系统，负责存储、检索和管理智能体的记忆（包括短期和长期）
"""

import os
import json
import logging
import uuid
import re # <--- Added missing import
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone

try:
    from utils.llm_service import LLMService
except ImportError:
    LLMService = None # type: ignore

logger = logging.getLogger("Hospital-MultiAgent-System")

DEFAULT_MEMORY_PATH = "data/hospital_memory_web.json" # Using separate file for web
SHORT_TERM_HOURS = 24

class MemorySystem:
    """记忆系统，管理患者信息、问诊记录、对话历史等"""

    # --- Corrected type hint syntax ---
    def __init__(self, persistence_path: Optional[str] = DEFAULT_MEMORY_PATH, llm_service: Optional[LLMService] = None):
    # ----------------------------------
        self.persistence_path = persistence_path
        self.llm_service = llm_service
        self._memory = self._load_memory()
        self._memory.setdefault("patients", {})
        self._memory.setdefault("global_events", [])
        self._memory.setdefault("active_consultations", {})
        logger.info(f"记忆系统初始化完成。持久化路径: {persistence_path or '无'}")
        if not llm_service:
             logger.warning("LLM 服务未提供给 MemorySystem，记忆归纳功能将不可用。")

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _is_short_term(self, timestamp_str: str) -> bool:
        try:
            timestamp_str = timestamp_str.replace('Z', '+00:00')
            entry_time = datetime.fromisoformat(timestamp_str)
            if entry_time.tzinfo is None: entry_time = entry_time.replace(tzinfo=timezone.utc)
            else: entry_time = entry_time.astimezone(timezone.utc)
            cutoff_time = self._now_utc() - timedelta(hours=SHORT_TERM_HOURS)
            return entry_time >= cutoff_time
        except (ValueError, TypeError):
            logger.warning(f"无法解析时间戳 '{timestamp_str}' 进行短期/长期判断，默认为长期。")
            return False

    def _load_memory(self) -> Dict[str, Any]:
        if self.persistence_path and os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r', encoding='utf-8') as f:
                    logger.info(f"从 {self.persistence_path} 加载记忆...")
                    loaded_data = json.load(f)
                    loaded_data.setdefault("patients", {})
                    loaded_data.setdefault("global_events", [])
                    loaded_data.setdefault("active_consultations", {})
                    return loaded_data
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载记忆文件 '{self.persistence_path}' 失败: {e}，将使用空记忆。")
        return {"patients": {}, "global_events": [], "active_consultations": {}}

    def _save_memory(self):
        if self.persistence_path:
            try:
                os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)
                with open(self.persistence_path, 'w', encoding='utf-8') as f:
                    json.dump(self._memory, f, indent=2, ensure_ascii=False, default=str)
                logger.debug(f"记忆已保存到 {self.persistence_path}")
            except IOError as e:
                logger.error(f"保存记忆文件 '{self.persistence_path}' 失败: {e}")
            except TypeError as e:
                 logger.error(f"序列化记忆时失败: {e}", exc_info=True)

    def _get_patient_data(self, patient_id: str, create_if_not_exists: bool = True) -> Optional[Dict[str, Any]]:
        patients = self._memory.setdefault("patients", {})
        if patient_id not in patients:
            if create_if_not_exists:
                logger.info(f"患者 {patient_id} 不存在，创建新的记忆记录。")
                patients[patient_id] = {"info": {},"memories": [],"consolidated_long_term": [],"conversation_history": [],"last_updated": self._now_utc().isoformat()}
            else: return None
        # Ensure essential keys exist
        patients[patient_id].setdefault("info", {})
        patients[patient_id].setdefault("memories", [])
        patients[patient_id].setdefault("consolidated_long_term", [])
        patients[patient_id].setdefault("conversation_history", [])
        patients[patient_id].setdefault("last_updated", self._now_utc().isoformat())
        return patients[patient_id]

    def add_or_update_patient_info(self, patient_id: str, info: Dict[str, Any]):
        logger.info(f"更新患者 {patient_id} 的基本信息: {info}")
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=True)
        if patient_data:
            patient_data.setdefault("info", {}).update(info)
            patient_data["last_updated"] = self._now_utc().isoformat()
            self._save_memory()

    def get_patient_info(self, patient_id: str) -> Optional[Dict[str, Any]]:
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        return patient_data.get("info") if patient_data else None

    def get_all_patients(self) -> Dict[str, Dict[str, Any]]:
         return {pid: data.get("info", {}) for pid, data in self._memory.get("patients", {}).items()}

    def get_all_patient_ids(self) -> List[str]:
        return list(self._memory.get("patients", {}).keys())

    def find_patients_by_attribute(self, attribute: str, value: Any) -> List[str]:
        matches = []
        for patient_id, data in self._memory.get("patients", {}).items():
            info = data.get("info", {})
            if info.get(attribute) == value: matches.append(patient_id)
        return matches

    def find_patient_by_phone(self, phone_number: str) -> Optional[str]:
        if not phone_number or not isinstance(phone_number, str): return None
        normalized_phone = "".join(filter(str.isdigit, phone_number))
        if not normalized_phone: logger.debug("Phone number became empty after normalization."); return None

        logger.debug(f"Searching for patient with normalized phone: {normalized_phone}")
        patients = self._memory.get("patients", {})
        for patient_id, data in patients.items():
            info = data.get("info", {})
            stored_phone_raw = info.get("phone")
            if stored_phone_raw:
                 normalized_stored_phone = "".join(filter(str.isdigit, str(stored_phone_raw)))
                 if normalized_phone == normalized_stored_phone:
                     logger.info(f"Found patient {patient_id} matching phone number.")
                     return patient_id
        logger.debug(f"No patient found matching phone number: {normalized_phone}")
        return None

    def add_patient_memory(self, patient_id: str, memory_type: str, data: Any, metadata: Optional[Dict[str, Any]] = None):
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=True)
        if not patient_data: return
        now_iso = self._now_utc().isoformat()
        if not metadata: metadata = {}
        metadata["timestamp_utc"] = now_iso
        memory_entry = {"memory_id": str(uuid.uuid4()),"type": memory_type, "data": data, "metadata": metadata, "consolidated": False}
        patient_data.setdefault("memories", []).append(memory_entry)
        patient_data["last_updated"] = now_iso
        logger.debug(f"为患者 {patient_id} 添加记忆 ({memory_type}): ID {memory_entry['memory_id']}")
        self._save_memory()

    def get_patient_memory(self, patient_id: str, memory_type: Optional[str] = None, time_window: Optional[str] = "all") -> List[Dict[str, Any]]:
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data: return []
        all_memories = patient_data.get("memories", [])
        results = []
        for entry in all_memories:
            type_match = (memory_type is None or entry.get("type") == memory_type)
            if not type_match: continue
            timestamp_str = entry.get("metadata", {}).get("timestamp_utc", "")
            is_short = self._is_short_term(timestamp_str) if timestamp_str else False
            time_match = False
            if time_window == "all": time_match = True
            elif time_window == "short_term" and is_short: time_match = True
            elif time_window == "long_term_unconsolidated" and not is_short and not entry.get("consolidated", False): time_match = True
            if time_match: results.append(entry)
        results.sort(key=lambda x: x.get("metadata", {}).get("timestamp_utc", "1970-01-01T00:00:00+00:00"))
        return results

    def mark_memories_consolidated(self, patient_id: str, memory_ids: List[str]):
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data or not memory_ids: return
        count = 0
        memories = patient_data.get("memories", [])
        for entry in memories:
            if entry.get("memory_id") in memory_ids:
                entry["consolidated"] = True
                count += 1
        if count > 0:
             patient_data["last_updated"] = self._now_utc().isoformat()
             self._save_memory()
             logger.info(f"已将患者 {patient_id} 的 {count} 条记忆标记为已归纳。")

    def add_conversation_entry(self, patient_id: str, role: str, content: Any, metadata: Optional[Dict[str, Any]] = None):
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=True)
        if not patient_data: return
        now_iso = self._now_utc().isoformat()
        if not metadata: metadata = {}
        metadata["timestamp_utc"] = now_iso
        entry = {"entry_id": str(uuid.uuid4()),"role": role,"content": content,"metadata": metadata}
        patient_data.setdefault("conversation_history", []).append(entry)
        patient_data["last_updated"] = now_iso
        logger.debug(f"为患者 {patient_id} 添加对话 (角色: {role}): ID {entry['entry_id']}")
        self._save_memory()

    def get_conversation_history(self, patient_id: str, limit: Optional[int] = None, roles: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data: return []
        history = patient_data.get("conversation_history", [])
        if roles: history = [entry for entry in history if entry.get("role") in roles]
        history.sort(key=lambda x: x.get("metadata", {}).get("timestamp_utc", "1970-01-01T00:00:00+00:00"))
        return history[-limit:] if limit is not None else history

    def save_consultation_context(self, context_id: str, context: Dict[str, Any]):
        if not context_id: logger.error("尝试保存上下文失败：未提供 context_id"); return
        active_consultations = self._memory.setdefault("active_consultations", {})
        context["last_updated_utc"] = self._now_utc().isoformat()
        active_consultations[context_id] = context
        logger.info(f"保存问诊上下文: {context_id} (Patient: {context.get('patient_id', 'N/A')})")
        self._save_memory()

    def get_consultation_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        if not context_id: return None
        context = self._memory.get("active_consultations", {}).get(context_id)
        if context: logger.debug(f"成功获取问诊上下文: {context_id}"); return context
        else: return None

    def update_consultation_context(self, context_id: str, updates: Dict[str, Any]):
        if not context_id: return
        active_contexts = self._memory.get("active_consultations", {})
        if context_id in active_contexts:
            active_contexts[context_id].update(updates)
            active_contexts[context_id]["last_updated_utc"] = self._now_utc().isoformat()
            logger.debug(f"更新问诊上下文: {context_id}")
            self._save_memory()
        else: logger.error(f"尝试更新不存在的问诊上下文: {context_id}")

    def delete_consultation_context(self, context_id: str):
        if not context_id: return
        active_consultations = self._memory.setdefault("active_consultations", {})
        deleted_context = active_consultations.pop(context_id, None)
        if deleted_context:
            logger.info(f"删除问诊上下文: {context_id} (Patient: {deleted_context.get('patient_id', 'N/A')})")
            self._save_memory()
        else: pass # Okay if context doesn't exist

    def consolidate_short_term_memory(self, patient_id: str) -> bool:
        logger.info(f"开始为患者 {patient_id} 尝试归纳短期记忆...")
        if not self.llm_service: logger.error(f"无法归纳记忆 (Patient: {patient_id})：LLM服务未初始化"); return False
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data: logger.warning(f"患者 {patient_id} 不存在，无法归纳。"); return False

        memories_to_consolidate = []
        memory_ids_to_mark = []
        for entry in patient_data.get("memories", []):
            if not entry.get("consolidated", False):
                 timestamp_str = entry.get("metadata", {}).get("timestamp_utc", "")
                 try:
                     if not self._is_short_term(timestamp_str):
                          memories_to_consolidate.append(entry)
                          memory_ids_to_mark.append(entry.get("memory_id"))
                 except Exception: logger.warning(f"跳过无法解析时间戳的记忆条目 {entry.get('memory_id')} for consolidation"); continue

        if not memories_to_consolidate: logger.info(f"患者 {patient_id} 没有需要归纳的过期短期记忆。"); return False

        logger.info(f"找到 {len(memories_to_consolidate)} 条需要归纳的记忆给患者 {patient_id}。")
        memories_to_consolidate.sort(key=lambda x: x.get("metadata", {}).get("timestamp_utc", ""))

        formatted_memories = []
        start_date, end_date = None, None
        for entry in memories_to_consolidate:
             ts_str = entry.get("metadata", {}).get("timestamp_utc", "未知时间")
             m_type = entry.get("type", "未知类型")
             try: m_data_str = (json.dumps(entry.get("data", {}), ensure_ascii=False, default=str, indent=1)[:200] + '...')
             except TypeError: m_data_str = str(entry.get("data", {}))[:200] + '...'
             formatted_memories.append(f"- 时间: {ts_str}, 类型: {m_type}, 内容: {m_data_str}")
             if ts_str != "未知时间":
                 try:
                     current_date_str = ts_str.split("T")[0]
                     if start_date is None or current_date_str < start_date: start_date = current_date_str
                     if end_date is None or current_date_str > end_date: end_date = current_date_str
                 except: pass
        memory_text = "\n".join(formatted_memories)
        memory_text = (memory_text[:3000] + "\n...") if len(memory_text) > 3000 else memory_text
        patient_info_str = json.dumps(patient_data.get("info", {}), ensure_ascii=False, default=str)
        period_covered = [start_date or "未知", end_date or "未知"]

        prompt = f"""请根据以下患者信息和近期（已超过{SHORT_TERM_HOURS}小时）的医疗记录，生成一份简洁的长期记忆摘要。

患者基本信息: {patient_info_str}

近期医疗记录:
{memory_text}

请分析这些记录，并以 JSON 格式总结以下关键信息:
{{
  "summary_date_utc": "{self._now_utc().isoformat()}",
  "period_covered": {json.dumps(period_covered)},
  "key_diagnoses": ["主要诊断列表，简洁"],
  "significant_symptoms": ["重要症状列表，简洁"],
  "treatments_procedures": ["主要治疗或操作列表"],
  "medication_summary": "用药情况总结，简洁",
  "overall_status_trend": "患者状态总体趋势描述",
  "follow_up_recommendations": ["后续重要建议列表"]
}}

请确保JSON格式正确，内容简洁且准确反映记录。如果记录不足以判断某项内容，请使用空列表[]或空字符串""。
"""
        try:
            response = self.llm_service.generate_response(prompt=prompt, system_message="你是一个专业的医疗记录摘要助手。请仔细分析提供的记录并生成准确、简洁的JSON格式摘要。", temperature=0.1, max_tokens=800)
            logger.debug(f"患者 {patient_id} 的记忆归纳LLM响应: {response}")

            # --- Use regex to extract JSON ---
            json_part = response.strip()
            match = re.search(r'\{.*\}', json_part, re.DOTALL) # Use imported re
            if match: json_part = match.group(0)
            else: raise ValueError("LLM response did not contain a valid JSON object structure.")
            # --------------------------------

            summary_data = json.loads(json_part)
            if not all(k in summary_data for k in ["key_diagnoses", "significant_symptoms", "medication_summary"]): raise ValueError("LLM summary missing required fields.")

            summary_metadata = {"consolidation_id": str(uuid.uuid4()),"consolidation_time_utc": self._now_utc().isoformat(),"consolidated_memory_ids": memory_ids_to_mark,"llm_model_used": getattr(self.llm_service.llm_config, 'get', lambda k, d=None: d)("deployment_name", "unknown")}
            patient_data.setdefault("consolidated_long_term", []).append({"summary": summary_data, "metadata": summary_metadata})
            self.mark_memories_consolidated(patient_id, memory_ids_to_mark)
            logger.info(f"成功为患者 {patient_id} 生成并存储了长期记忆摘要。")
            return True
        except (json.JSONDecodeError, ValueError, Exception) as e:
            logger.error(f"处理记忆归纳LLM响应时出错: {e}. Raw Response: {response if 'response' in locals() else 'N/A'}", exc_info=True)
            return False

    def get_consolidated_long_term_memories(self, patient_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data: return []
        consolidated = patient_data.get("consolidated_long_term", [])
        consolidated.sort(key=lambda x: x.get("metadata", {}).get("consolidation_time_utc", "1970-01-01T00:00:00+00:00"), reverse=True)
        return consolidated[:limit] if limit is not None else consolidated

    def get_all_memory_categories(self, patient_id: str) -> Dict[str, Any]:
        stats = {"short_term_unconsolidated_count": 0,"long_term_unconsolidated_count": 0,"consolidated_short_term_count": 0,"long_term_summary_count": 0,"conversation_history_count": 0,"memory_types_distribution": {}}
        patient_data = self._get_patient_data(patient_id, create_if_not_exists=False)
        if not patient_data: return stats
        type_dist = {}
        for entry in patient_data.get("memories", []):
            m_type = entry.get("type", "unknown"); type_dist[m_type] = type_dist.get(m_type, 0) + 1
            is_consolidated = entry.get("consolidated", False)
            timestamp_str = entry.get("metadata", {}).get("timestamp_utc", "")
            is_short = self._is_short_term(timestamp_str) if timestamp_str else False
            if is_consolidated: stats["consolidated_short_term_count"] += 1
            elif is_short: stats["short_term_unconsolidated_count"] += 1
            else: stats["long_term_unconsolidated_count"] += 1
        stats["long_term_summary_count"] = len(patient_data.get("consolidated_long_term", []))
        stats["conversation_history_count"] = len(patient_data.get("conversation_history", []))
        stats["memory_types_distribution"] = type_dist
        return stats