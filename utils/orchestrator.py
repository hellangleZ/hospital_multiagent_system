#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
编排器组件，负责协调多智能体之间的消息传递和流程管理
支持通过 MemorySystem 管理状态，并处理 Web 应用的交互请求
"""

import logging
import uuid
import json
import re
import os
from datetime import datetime, timezone # Make sure timezone is imported
from typing import Dict, List, Any, Optional, Tuple

try:
    from agents.base_agent import BaseAgent
    # Correctly import stages from receptionist
    from agents.receptionist import ReceptionistAgent, STAGE_INTENT, STAGE_ASKING_IDENTITY, STAGE_GUIDING, STAGE_CHATTING, STAGE_CHAT_ENDED, STAGE_CLARIFICATION, STAGE_ERROR, STAGE_COMPLETED
    from agents.doctor import DoctorAgent
    from agents.pharmacist import PharmacistAgent
    from agents.scheduler import SchedulerAgent
    from utils.memory_system import MemorySystem
except ImportError as e:
    logging.critical(f"Orchestrator 无法导入核心依赖: {e}", exc_info=True)
    class PlaceholderAgent: pass
    class PlaceholderMemorySystem: pass
    BaseAgent = PlaceholderAgent # type: ignore
    ReceptionistAgent = DoctorAgent = PharmacistAgent = SchedulerAgent = PlaceholderAgent # type: ignore
    MemorySystem = PlaceholderMemorySystem # type: ignore
    STAGE_INTENT=STAGE_ASKING_IDENTITY=STAGE_GUIDING=STAGE_CHATTING=STAGE_CHAT_ENDED=STAGE_CLARIFICATION=STAGE_ERROR=STAGE_COMPLETED="unknown_stage"


logger = logging.getLogger("Hospital-MultiAgent-System")

DEFAULT_DEPARTMENT = "内科"

class Orchestrator:
    """编排器，负责协调医院多智能体系统的交互流程"""

    def __init__(self,
                 receptionist: Optional[ReceptionistAgent] = None,
                 doctor: Optional[DoctorAgent] = None,
                 pharmacist: Optional[PharmacistAgent] = None,
                 scheduler: Optional[SchedulerAgent] = None,
                 memory_system: Optional[MemorySystem] = None):

        if not isinstance(receptionist, ReceptionistAgent): raise TypeError("必须提供有效的 ReceptionistAgent 实例。")
        if not isinstance(doctor, DoctorAgent): raise TypeError("必须提供有效的 DoctorAgent 实例。")
        if not isinstance(pharmacist, PharmacistAgent): raise TypeError("必须提供有效的 PharmacistAgent 实例。")
        if not isinstance(memory_system, MemorySystem): raise TypeError("必须提供有效的 MemorySystem 实例。")
        if scheduler and not isinstance(scheduler, SchedulerAgent): logger.warning("提供的 Scheduler 无效或类型错误，将忽略。"); scheduler = None

        self.receptionist = receptionist
        self.doctor = doctor
        self.pharmacist = pharmacist
        self.scheduler = scheduler
        self.memory_system = memory_system
        self.agents: Dict[str, BaseAgent] = {"receptionist": receptionist,"doctor": doctor,"pharmacist": pharmacist}
        if scheduler: self.agents["scheduler"] = scheduler
        logger.info("编排器初始化完成")

    def _log_interaction_event(self, consultation_id: str, event_details: Dict[str, Any]):
        """记录交互事件到会话上下文，确保日志包含足够信息在前端显示，并保存到文件"""
        if not consultation_id or not self.memory_system: 
            return
            
        try:
            # 获取当前上下文
            context = self.memory_system.get_consultation_context(consultation_id)
            if not context:
                logger.warning(f"无法记录交互事件: 找不到上下文 {consultation_id}")
                return
                
            # 确保交互日志列表存在
            context.setdefault("interaction_log", [])
            
            # 添加时间戳
            event_details["timestamp"] = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"
            
            # 确保详情字段存在，并且至少包含基本信息
            event_details.setdefault("details", {})
            
            # 为不同类型的交互添加更丰富的信息
            source = event_details.get("source", "")
            target = event_details.get("target", "")
            action = event_details.get("action", "")
            
            # 根据不同的交互类型，丰富详情信息
            if "发送请求" in action or "触发" in action:
                # 添加请求类型说明
                if "content_keys" in event_details.get("details", {}):
                    keys = event_details["details"]["content_keys"]
                    if isinstance(keys, list) and len(keys) > 0:
                        event_details["details"]["request_type"] = keys[0]
                        
            elif "收到响应" in action or "收到审核结果" in action:
                # 添加状态描述
                status = event_details.get("details", {}).get("status")
                if status:
                    event_details["details"]["status_description"] = self._get_status_description(status)
                    
            elif "用户输入" in action:
                # 保持消息片段
                pass
                
            elif "错误" in action:
                # 确保错误详情可见
                pass
                
            # 添加适合人类阅读的描述
            event_details["human_readable"] = self._generate_human_readable_description(source, target, action, event_details.get("details", {}))
            
            # 添加到日志列表
            context["interaction_log"].append(event_details)
            
            # 限制日志大小
            context["interaction_log"] = context["interaction_log"][-50:]
            
            # 更新上下文
            self.memory_system.update_consultation_context(consultation_id, {"interaction_log": context["interaction_log"]})
            
            # 记录日志项
            log_msg = f"Event Logged [{consultation_id}]: {source} -> {target} ({action})"
            if 'status' in event_details.get('details', {}): 
                log_msg += f" Status: {event_details['details']['status']}"
            logger.debug(log_msg)
            
            # 保存交互日志到文件
            self._save_interaction_log_to_file(consultation_id, event_details)
            
        except Exception as e:
            logger.error(f"Failed to log interaction event for {consultation_id}: {e}", exc_info=True)
    
    def _save_interaction_log_to_file(self, consultation_id: str, event_details: Dict[str, Any]):
        """保存交互日志到文件，以便在会话结束后仍然可以查看"""
        try:
            # 日志文件路径，以consultation_id命名
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            log_file_path = os.path.join(log_dir, f"interaction_log_{consultation_id}.json")
            
            # 准备要写入的数据
            log_entry = {
                "timestamp": event_details.get("timestamp", datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"),
                "source": event_details.get("source", "unknown"),
                "target": event_details.get("target", "unknown"),
                "action": event_details.get("action", "unknown"),
                "details": event_details.get("details", {}),
                "human_readable": event_details.get("human_readable", "")
            }
            
            # 读取现有日志文件（如果存在）
            existing_logs = []
            if os.path.exists(log_file_path):
                try:
                    with open(log_file_path, 'r', encoding='utf-8') as f:
                        existing_logs = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"无法解析现有日志文件 {log_file_path}，将创建新文件")
            
            # 追加新日志
            existing_logs.append(log_entry)
            
            # 写回文件
            with open(log_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"已将交互事件保存到文件 {log_file_path}")
            
        except Exception as e:
            logger.error(f"保存交互日志到文件时出错: {e}", exc_info=True)

    def _get_status_description(self, status: str) -> str:
        """根据状态码返回人类可读的状态描述"""
        status_descriptions = {
            # 医生状态
            "in_consultation": "问诊进行中",
            "diagnosis_complete": "诊断已完成",
            
            # 药剂师状态
            "approved": "处方已通过",
            "rejected": "处方未通过",
            "info_provided": "已提供用药信息",
            "interactions_found": "发现药物相互作用",
            "no_interactions_found": "无药物相互作用",
            
            # 接待状态
            "in_progress": "接待进行中",
            "completed": "接待完成",
            
            # 通用状态
            "error": "出现错误",
            "success": "成功",
            "unhandled": "未处理",
        }
        return status_descriptions.get(status, status)
        
    def _generate_human_readable_description(self, source: str, target: str, action: str, details: Dict[str, Any]) -> str:
        """生成人类可读的事件描述"""
        # 初始信息
        description = ""
        
        # 处理不同类型的源
        if source == "User":
            description = "用户发送消息"
        elif source == "System":
            description = "系统"
        elif source == "Orchestrator":
            if "触发" in action:
                if target == "Doctor":
                    description = "系统将患者转给医生进行诊断"
                elif target == "Pharmacist":
                    description = "系统请求药剂师审核处方"
                else:
                    description = f"系统触发{target}服务"
            else:
                description = f"系统向{target}发送请求"
        elif source == "receptionist":
            description = "接待员完成接待流程"
        elif source == "doctor":
            if action == "收到诊断触发响应":
                description = "医生开始诊断"
            elif "诊断" in action:
                description = "医生完成诊断"
            else:
                description = "医生回复"
        elif source == "pharmacist":
            status = details.get("status", "")
            if status == "approved":
                description = "药剂师审核通过处方"
            elif status == "rejected":
                description = "药剂师发现处方问题"
            else:
                description = "药剂师提供用药指导"
        
        # 添加详情
        if "error" in details:
            description += f"（错误：{details['error']}）"
        elif "message" in details:
            description += f"（{details['message']}）"
        elif "status_description" in details:
            description += f"（{details['status_description']}）"
            
        return description

    def start_new_web_consultation(self) -> Tuple[str, str]:
        consultation_id = f"web_{uuid.uuid4()}"
        logger.info(f"Orchestrator: 开始新的 Web 咨询，ID: {consultation_id}")
        initial_message = "您好，欢迎来到智能医院问诊系统。为了更好地帮助您，请描述您的主要症状，如果方便，也请告知您的年龄。"
        return consultation_id, initial_message

    def handle_web_message(self, consultation_id: str, user_message: str) -> Dict[str, Any]:
        logger.info(f"Orchestrator: 处理 Web 消息 (Consultation: {consultation_id}): '{user_message[:50]}...'")
        if not all(agent in self.agents for agent in ["receptionist", "doctor", "pharmacist"]) or not self.memory_system:
             logger.error(f"Orchestrator 缺少核心组件 (Consultation: {consultation_id})")
             return {"status": "error", "message": "系统内部错误，核心服务不可用。", "agent_type":"system"}

        active_context = self.memory_system.get_consultation_context(consultation_id)
        target_agent: Optional[BaseAgent] = None
        agent_input_content: Optional[Dict[str, Any]] = None
        patient_id: Optional[str] = None
        request_key_for_log: str = "unknown_request"

        if active_context:
             patient_id = active_context.get("patient_id")
             # --- Log User Input ---
             self._log_interaction_event(consultation_id, {
                 "source": "User", "target": "System", "action": "用户输入",
                 "details": {"message_snippet": user_message[:30]+"..."}
             })
             # --- Determine Target ---
             # ... (rest of logic to determine target_agent, agent_input_content, request_key_for_log based on context.get('stage')) ...
             current_stage = active_context.get("stage", "unknown")
             logger.info(f"找到活跃上下文 {consultation_id} (Patient ID in context: {patient_id}), 当前阶段: {current_stage}")
             if current_stage in [STAGE_INTENT, STAGE_ASKING_IDENTITY, STAGE_GUIDING, STAGE_CHATTING, STAGE_CHAT_ENDED, STAGE_CLARIFICATION, STAGE_ERROR]:
                 target_agent = self.agents.get("receptionist")
                 agent_input_content = {"followup_query": {"query": user_message, "patient_id": patient_id, "context_id": consultation_id}}
                 request_key_for_log = "followup_query"
             elif current_stage == "information_gathering":
                 target_agent = self.agents.get("doctor")
                 agent_input_content = {"patient_response": {"patient_id": patient_id, "answer": user_message, "context_id": consultation_id}}
                 request_key_for_log = "patient_response"
             elif current_stage == "prescription_review":
                 target_agent = self.agents.get("pharmacist")
                 last_prescription = active_context.get("last_prescription_for_query")
                 if not last_prescription: logger.warning(f"Pharmacist query received for {consultation_id} but no prescription found."); return {"status": "error", "message": "无法处理您的问题，当前没有关联的处方信息。", "agent_type":"system"}
                 agent_input_content = {"patient_query_about_prescription": {"patient_id": patient_id,"query": user_message,"prescription": last_prescription,"context_id": consultation_id}}
                 request_key_for_log = "patient_query_about_prescription"
             else:
                 logger.warning(f"上下文 {consultation_id} 处于未处理阶段: {current_stage}，转给接待员。")
                 target_agent = self.agents.get("receptionist")
                 if not patient_id: # Safeguard
                      extracted_info = self._extract_info_from_initial_message(user_message); patient_id = self._get_or_create_patient_id(extracted_info.get("name"), extracted_info.get("age"))
                      self._log_interaction_event(consultation_id, {"source": "User", "target": "System", "action": "用户输入 (无上下文)", "details": {"message_snippet": user_message[:30]+"..."}}) # Log again if context was missing
                      agent_input_content = {"reception_request": {"patient_id": patient_id,"patient_name": extracted_info.get("name", "网页用户"),"patient_age": extracted_info.get("age"), "symptoms": extracted_info.get("symptoms", []),"raw_message": user_message, "consultation_id": consultation_id}}
                      request_key_for_log = "reception_request"
                 else:
                      agent_input_content = {"followup_query": {"query": user_message, "patient_id": patient_id, "context_id": consultation_id}}
                      request_key_for_log = "followup_query"
        else: # No active context - First message
            logger.info(f"没有找到活跃上下文 {consultation_id}，视为新对话，转给接待员。")
            target_agent = self.agents.get("receptionist")
            # --- FIX: Call the method using self. ---
            extracted_info = self._extract_info_from_initial_message(user_message)
            patient_id = self._get_or_create_patient_id(extracted_info.get("name"), extracted_info.get("age"))
            # ------------------------------------------
            # Log user input now that we have patient_id
            self._log_interaction_event(consultation_id, {"source": "User", "target": "System", "action": "用户输入 (首次)", "details": {"message_snippet": user_message[:30]+"..."}})
            agent_input_content = {"reception_request": {"patient_id": patient_id,"patient_name": extracted_info.get("name", "网页用户"),"patient_age": extracted_info.get("age"),"symptoms": extracted_info.get("symptoms", []),"raw_message": user_message,"consultation_id": consultation_id}}
            request_key_for_log = "reception_request"

        if not target_agent or not agent_input_content:
             logger.error(f"无法确定处理消息的目标 Agent 或输入内容 (Consultation: {consultation_id})")
             if consultation_id: self.memory_system.delete_consultation_context(consultation_id)
             return {"status": "error", "message": "系统内部错误，无法处理您的请求。", "agent_type":"system"}

        try:
            logger.info(f"将消息转发给 Agent: {target_agent.role} (Name: {target_agent.name}), Consultation: {consultation_id}")
            self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": target_agent.role,"action": f"发送请求 ({request_key_for_log})","details": {"content_keys": list(agent_input_content.keys())}})
            agent_message_envelope = {"sender_id": "orchestrator_web_handler","sender_role": "orchestrator","content": agent_input_content,"consultation_id": consultation_id,"patient_id": patient_id}
            agent_response_msg = target_agent.receive_message(agent_message_envelope)
            resp_content_keys = list(agent_response_msg.get("content", {}).keys()); resp_status = agent_response_msg.get("content", {}).get("status", "unknown")
            self._log_interaction_event(consultation_id, {"source": target_agent.role, "target": "Orchestrator","action": "收到响应","details": {"status": resp_status, "content_keys": resp_content_keys}})
            return self._process_agent_response_for_web(consultation_id, agent_response_msg, patient_id)
        except Exception as e:
             logger.error(f"与 Agent ({target_agent.role}) 交互时出错 (Consultation: {consultation_id}): {e}", exc_info=True)
             self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": target_agent.role, "action": "交互错误","details": {"error": str(e)}})
             if consultation_id: self.memory_system.delete_consultation_context(consultation_id)
             return {"status": "error", "message": f"系统在与 {target_agent.role} 沟通时出现问题，请稍后重试。", "agent_type":"system"}


    # --- REINSTATED HELPER METHODS ---
    def _extract_info_from_initial_message(self, message: str) -> Dict[str, Any]:
        """Extracts basic info (age, symptoms) from the first user message."""
        logger.debug(f"尝试从初始消息提取信息: '{message[:100]}...'")
        symptoms = []; age = None; name = None
        age_match = re.search(r'(\d{1,3})\s*(?:岁|周岁|years old)', message, re.IGNORECASE)
        if age_match:
            try: age_val = int(age_match.group(1)); age = age_val if 0 < age_val < 120 else None
            except ValueError: pass
        symptom_keywords = ["症状", "感觉", "不适", "问题", "头痛", "咳嗽", "发烧", "腹泻", "呕吐", "恶心", "乏力", "疼痛", "胸闷", "流涕"]
        potential_symptom_text = message
        for keyword in symptom_keywords:
            if keyword in message: parts = re.split(f'{keyword}[是为有：:]*', message, maxsplit=1, flags=re.IGNORECASE); potential_symptom_text = parts[1] if len(parts) > 1 else potential_symptom_text; break
        delimiters = r'[，。；、？！,.!?\s]+'
        possible_symptoms = re.split(delimiters, potential_symptom_text.strip())
        symptoms = [s.strip() for s in possible_symptoms if s.strip() and len(s.strip()) > 1 and not s.strip().isdigit() and s.strip() not in ["你好","请问","医生","我", "谢谢", "麻烦", "嗯", "啊", "呢"]]
        if not symptoms: symptoms = ["身体不适"] if any(word in message for word in ["不舒服", "难受", "生病了"]) else ["用户描述不清晰"]
        logger.debug(f"提取结果: Age={age}, Symptoms={symptoms}")
        return {"symptoms": symptoms, "age": age, "name": name}

    def _get_or_create_patient_id(self, patient_name: Optional[str], patient_age: Optional[int]) -> str:
        """Creates a new temporary patient ID for web interaction."""
        web_patient_id = f"WebPatient_{uuid.uuid4().hex[:8]}"
        info_to_add = {"name": patient_name or "网页用户","age": patient_age,"source": "web","created_utc": datetime.now(timezone.utc).isoformat()}
        if self.memory_system: self.memory_system.add_or_update_patient_info(web_patient_id, info_to_add); logger.info(f"为网页交互创建初始患者 ID: {web_patient_id} (Name: {patient_name or '网页用户'}, Age: {patient_age})")
        else: logger.error("MemorySystem not available in _get_or_create_patient_id"); return "error_creating_id"
        return web_patient_id
    # --- END REINSTATED HELPER METHODS ---


    def _process_agent_response_for_web(self, consultation_id: str, agent_response: Dict[str, Any], current_turn_patient_id: Optional[str]) -> Dict[str, Any]:
        if not agent_response or not isinstance(agent_response, dict): 
            logger.error(f"收到无效的 Agent 响应 (Consultation: {consultation_id}): {agent_response}")
            return {"status": "error", "message": "系统内部通信错误。", "agent_type": "system"}
        
        agent_role = agent_response.get("sender_role", "system")
        content = agent_response.get("content", {})
        status_from_agent = content.get("status", "unknown")
        next_stage_from_agent = content.get("next_stage")
        
        # Ensure the message field is always a valid string
        default_message = f"来自 {agent_role} 的响应处理中..."
        message_from_agent = content.get("message", default_message)
        if message_from_agent is None or not isinstance(message_from_agent, str):
            message_from_agent = default_message
            logger.warning(f"Agent返回了非字符串消息 (Consultation: {consultation_id}, Role: {agent_role}), 使用默认消息")
        
        web_response = {
            "agent_type": agent_role,
            "message": message_from_agent,
            "status": "in_progress",
            "consultation_id": consultation_id,
            "prescription": None,
            "diagnosis_info": None,
            "context_id": consultation_id
        }
        
        logger.debug(f"处理来自 {agent_role} 的响应 (AgentStatus: {status_from_agent}, NextStage: {next_stage_from_agent}), Content Keys: {list(content.keys())}")

        if agent_role == "receptionist":
            reception_result = content.get("reception_result")
            current_reception_stage = next_stage_from_agent or status_from_agent
            if current_reception_stage == STAGE_COMPLETED:
                logger.info(f"接待流程完成 (Consultation: {consultation_id})，准备触发医生诊断。")
                if reception_result and reception_result.get("status") == "success":
                    final_patient_id = reception_result.get("patient_id")
                    if not final_patient_id: 
                        logger.error(f"接待完成但未返回有效的 patient_id (Consultation: {consultation_id})")
                        web_response.update({"status": "error", "message": "系统错误：无法确定患者身份。"})
                        self.memory_system.delete_consultation_context(consultation_id)
                        self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": "接待完成但无 patient_id"}})
                    else:
                        self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "Doctor", "action": "触发诊断", "details": {"patient_id": final_patient_id}})
                        doctor_response = self._trigger_doctor_diagnosis(consultation_id, final_patient_id, reception_result)
                        doc_content = doctor_response.get("content", {})
                        doc_status = doc_content.get("status")
                        self._log_interaction_event(consultation_id, {"source": "Doctor", "target": "Orchestrator", "action": "收到诊断触发响应", "details": {"status": doc_status}})
                        
                        if doc_status == "in_consultation": 
                            web_response["agent_type"] = "doctor"
                            doctor_question = doc_content.get("question")
                            # Ensure doctor_question is a string
                            if not doctor_question or not isinstance(doctor_question, str):
                                doctor_question = "医生需了解更多信息"
                            web_response["message"] = doctor_question
                            web_response["context_id"] = doc_content.get("context_id")
                            web_response["status"] = "in_progress"
                            logger.info(f"成功转接给医生 (Consultation: {consultation_id})")
                        elif doc_status == "diagnosis_complete": 
                            logger.warning(f"医生首次交互后直接诊断 (Consultation: {consultation_id})")
                            web_response["agent_type"] = "doctor"
                            process_result = self._process_doctor_diagnosis_complete(consultation_id, final_patient_id, doc_content)
                            web_response.update(process_result)
                        else: 
                            error_msg = doc_content.get("message", "转接医生时出错")
                            if not isinstance(error_msg, str):
                                error_msg = "转接医生时出错"
                            web_response.update({"status": "error", "message": error_msg})
                            self.memory_system.delete_consultation_context(consultation_id)
                            self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"医生触发失败: {error_msg}"}})
                else: 
                    fail_reason = reception_result.get('message', '未知') if reception_result else '未知'
                    if not isinstance(fail_reason, str):
                        fail_reason = '未知'
                    web_response["message"] = f"抱歉，分诊失败 ({fail_reason})"
                    web_response["status"] = "error"
                    self.memory_system.delete_consultation_context(consultation_id)
                    self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"分诊失败: {fail_reason}"}})
            elif status_from_agent == "in_progress" or current_reception_stage != STAGE_COMPLETED: 
                web_response["status"] = "in_progress"
            else: 
                web_response["status"] = "error"
                error_msg = content.get("message", "接待处理时未知错误")
                if not isinstance(error_msg, str):
                    error_msg = "接待处理时未知错误"
                web_response["message"] = error_msg
                self.memory_system.delete_consultation_context(consultation_id)
                self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"接待员返回未知状态: {status_from_agent}"}})
        
        elif agent_role == "doctor":
            context_id_from_doctor = content.get("context_id", consultation_id)
            web_response["context_id"] = context_id_from_doctor
            if status_from_agent == "in_consultation": 
                doctor_question = content.get("question")
                if not doctor_question or not isinstance(doctor_question, str):
                    doctor_question = "医生需了解更多信息"
                web_response["message"] = doctor_question
                web_response["status"] = "in_progress"
            elif status_from_agent == "diagnosis_complete": 
                logger.info(f"医生完成诊断 (Consultation: {consultation_id}, Patient: {current_turn_patient_id})")
                process_result = self._process_doctor_diagnosis_complete(consultation_id, current_turn_patient_id, content)
                web_response.update(process_result)
            else: 
                error_msg = content.get("message", "医生处理时出错")
                if not isinstance(error_msg, str):
                    error_msg = "医生处理时出错"
                web_response["message"] = error_msg
                web_response["status"] = "error"
                self.memory_system.delete_consultation_context(context_id_from_doctor)
                self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"医生返回错误/未知状态: {status_from_agent}"}})
        
        elif agent_role == "pharmacist":
            context_id_from_pharmacist = content.get("context_id", consultation_id)
            web_response["context_id"] = context_id_from_pharmacist
            if status_from_agent in ["info_provided", "interactions_found", "no_interactions_found"]: 
                pharmacist_message = content.get("message", "药剂师已提供信息")
                if not isinstance(pharmacist_message, str):
                    pharmacist_message = "药剂师已提供信息"
                web_response["message"] = pharmacist_message
                web_response["status"] = "info_displayed"
            else: 
                error_msg = content.get("message", "药剂师处理时出错")
                if not isinstance(error_msg, str):
                    error_msg = "药剂师处理时出错"
                web_response["message"] = error_msg
                web_response["status"] = "error"
        
        elif status_from_agent == 'unhandled': 
            error_msg = content.get("message", "系统无法处理请求")
            if not isinstance(error_msg, str):
                error_msg = "系统无法处理请求"
            web_response["message"] = error_msg
            web_response["status"] = "error"
            self.memory_system.delete_consultation_context(consultation_id)
            self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"{agent_role}无法处理请求"}})
        
        elif status_from_agent == "error": 
            error_msg = content.get("message", "处理时未知错误")
            if not isinstance(error_msg, str):
                error_msg = "处理时未知错误"
            web_response["message"] = error_msg
            web_response["status"] = "error"
            self.memory_system.delete_consultation_context(consultation_id)
            self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "错误", "details": {"message": f"{agent_role}报告错误: {error_msg}"}})

        final_context = self.memory_system.get_consultation_context(consultation_id)
        web_response["interaction_log"] = final_context.get("interaction_log", []) if final_context else [{"timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z", "source":"System", "target":"", "action":"错误", "details": "无法检索日志"}]

        terminal_status_web = ["completed_no_prescription", "completed_prescription", "error_prescription_rejected", "error"]
        if web_response["status"] in terminal_status_web: 
            logger.info(f"Web 咨询 {consultation_id} 结束: {web_response['status']}")
            self._log_interaction_event(consultation_id, {"source": "System", "target": "", "action": "咨询结束", "details": {"status": web_response['status']}})

        final_patient_id_for_log = final_context.get("patient_id") if final_context else current_turn_patient_id
        if log_patient_id := final_patient_id_for_log: 
            self.memory_system.add_conversation_entry(log_patient_id, web_response["agent_type"], web_response["message"], metadata={"source": "orchestrator_web_final_response","consultation_id": consultation_id,"web_status": web_response["status"]})
        
        logger.info(f"Orchestrator: 返回给 Web (Consultation: {consultation_id}): Status={web_response['status']}, Agent={web_response['agent_type']}, Msg='{web_response['message'][:70]}...'")
        return web_response

    def _process_doctor_diagnosis_complete(self, consultation_id: str, patient_id: Optional[str], doctor_content: Dict[str, Any]) -> Dict[str, Any]:
        result_data = doctor_content.get("diagnosis_result", {})
        processed_response = {"status": "error", "message": "处理诊断结果时出错。", "prescription": None, "diagnosis_info": None}
        context_id_to_use = doctor_content.get("context_id", consultation_id)
        
        self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "System", "action": "处理医生诊断结果", "details": {"status": result_data.get("status")}})
        
        if not patient_id:
            logger.error(f"Cannot process diagnosis complete: Patient ID is missing (Consultation: {consultation_id})")
            processed_response["message"] = "内部错误：无法处理诊断结果，患者信息丢失。"
            self.memory_system.delete_consultation_context(context_id_to_use)
            return processed_response
            
        if result_data.get("status") == "success":
            diagnosis = result_data.get("diagnosis", {})
            processed_response["message"] = result_data.get("message", "诊断已完成。")
            processed_response["diagnosis_info"] = {
                "condition": diagnosis.get("condition"),
                "explanation": diagnosis.get("explanation"),
                "severity": diagnosis.get("severity"),
                "diagnostic_tests": diagnosis.get("diagnostic_tests", [])
            }
            
            meds = diagnosis.get("medications", [])
            meds = [m for m in meds if isinstance(m, dict)] if isinstance(meds, list) else []
            original_prescription = {
                "medications": meds,
                "instructions": diagnosis.get("recommendations", []),
                "notes": diagnosis.get("follow_up", "")
            }
            
            if original_prescription["medications"]:
                logger.info(f"诊断完成，需开药，触发审核 (Patient: {patient_id}, Context: {context_id_to_use})")
                self._log_interaction_event(consultation_id, {"source": "Orchestrator", "target": "Pharmacist", "action": "触发处方审核", "details": {"num_meds": len(original_prescription["medications"])}})
                pharmacist_response = self._trigger_prescription_review(patient_id, diagnosis, original_prescription)
                pharma_content = pharmacist_response.get("content", {})
                review_result = pharma_content.get("review_result", {})
                pharma_status = review_result.get("status", "unknown")
                self._log_interaction_event(consultation_id, {"source": "Pharmacist", "target": "Orchestrator", "action": "收到审核结果", "details": {"status": pharma_status}})
                
                if pharma_status == "approved":
                    final_prescription = review_result.get("prescription", original_prescription)
                    processed_response["prescription"] = final_prescription
                    processed_response["message"] += "\n" + review_result.get("notes", "药剂师已审核通过处方。")
                    processed_response["status"] = "completed_prescription"
                    active_context = self.memory_system.get_consultation_context(context_id_to_use)
                    logger.info(f"处方审核通过 (Consultation: {context_id_to_use})")
                    if active_context:
                        active_context["last_prescription_for_query"] = final_prescription
                        active_context["stage"] = "prescription_review"
                        self.memory_system.update_consultation_context(context_id_to_use, active_context)
                else:
                    processed_response["prescription"] = None
                    reject_message = review_result.get("message", "但处方审核未通过。")
                    issues = review_result.get("issues", [])
                    reject_message += f" 问题: {', '.join(issues)}" if issues else ""
                    processed_response["message"] += "\n" + reject_message
                    processed_response["status"] = "error_prescription_rejected"
                    logger.warning(f"处方审核被拒绝 (Consultation: {context_id_to_use}): {issues}")
                    self.memory_system.delete_consultation_context(context_id_to_use)
            else:
                logger.info(f"诊断完成，无需开药。 (Patient: {patient_id}, Context: {context_id_to_use})")
                processed_response["prescription"] = None
                processed_response["status"] = "completed_no_prescription"
                self.memory_system.delete_consultation_context(context_id_to_use)
        else:
            processed_response["message"] = result_data.get("message", "医生诊断时出错")
            self.memory_system.delete_consultation_context(context_id_to_use)
            
        return processed_response

    def _trigger_doctor_diagnosis(self, consultation_id: str, patient_id: str, reception_result: Dict) -> Dict[str, Any]:
        if not self.doctor:
            logger.error(f"无法触发医生诊断：医生实例未初始化 (Patient: {patient_id})")
            return {"status": "error", "content": {"message": "医生服务内部错误"}}
        if not patient_id:
            logger.error(f"无法触发医生诊断：无效的 patient_id (Consultation: {consultation_id})")
            return {"status": "error", "content": {"message": "内部错误：患者ID无效"}}
            
        logger.info(f"触发医生诊断流程 (Consultation: {consultation_id}, Patient: {patient_id})...")
        try:
            context = self.memory_system.get_consultation_context(consultation_id)
            if not context:
                logger.error(f"无法触发诊断：找不到咨询上下文 {consultation_id}")
                return {"status": "error", "content": {"message": "无法找到咨询状态"}}
                
            symptoms = context.get("extracted_symptoms", [])
            patient_info_final = reception_result.get("patient_info_final", {})
            medical_history_summary = []
            
            if context.get("identity_confirmed"):
                summaries = self.memory_system.get_consolidated_long_term_memories(patient_id, limit=1)
                if summaries:
                    latest_summary = summaries[0].get('summary', {})
                    diag_summary = ", ".join(latest_summary.get('key_diagnoses', []))
                    treat_summary = ", ".join(latest_summary.get('treatments_procedures', []))
                    med_summary = latest_summary.get('medication_summary', '')
                    medical_history_summary.extend([f"过往主要诊断: {d}" for d in [diag_summary, treat_summary, med_summary] if d])
                if not medical_history_summary:
                    medical_history_summary.append("有就诊记录但无摘要信息")
                    
            diagnosis_request_content = {
                "diagnose_request": {
                    "patient_id": patient_id,
                    "symptoms": symptoms,
                    "medical_history": medical_history_summary,
                    "department": reception_result.get("department", DEFAULT_DEPARTMENT),
                    "is_return_visit": context.get("is_return_visit", False),
                    "previous_diagnosis": None,
                    "reception_notes": reception_result.get("notes"),
                    "consultation_id": consultation_id
                }
            }
            
            doctor_initial_response = self.doctor.receive_message({
                "sender_id": "orchestrator_trigger",
                "sender_role": "orchestrator",
                "content": diagnosis_request_content,
                "consultation_id": consultation_id,
                "patient_id": patient_id
            })
            
            doc_resp_status = doctor_initial_response.get('content', {}).get('status', 'unknown')
            logger.info(f"医生对初始诊断请求的响应状态: {doc_resp_status} (Consultation: {consultation_id})")
            return doctor_initial_response
        except Exception as e:
            logger.error(f"触发医生诊断时失败 (Consultation: {consultation_id}, Patient: {patient_id}): {e}", exc_info=True)
            return {"status": "error", "content": {"message": f"触发医生诊断时出错: {e}"}}

    def _trigger_prescription_review(self, patient_id: str, diagnosis: Dict[str, Any], prescription: Dict[str, Any]) -> Dict[str, Any]:
        if not self.pharmacist:
            logger.error(f"无法触发处方审核：药剂师实例未初始化 (Patient: {patient_id})")
            return {"status": "error", "content": {"review_result": {"status": "error", "message": "药剂师服务不可用"}}}
        if not patient_id:
            logger.error(f"无法触发处方审核：无效的 patient_id")
            return {"status": "error", "content": {"review_result": {"status": "error", "message": "内部错误：患者ID无效"}}}
            
        logger.info(f"向药剂师发送处方审核请求 (Patient: {patient_id})...")
        try:
            review_request_content = {
                "review_request": {
                    "patient_id": patient_id,
                    "diagnosis": {
                        "condition": diagnosis.get("condition"),
                        "severity": diagnosis.get("severity"),
                        "explanation": diagnosis.get("explanation")
                    },
                    "prescription": prescription
                }
            }
            
            pharmacist_response = self.pharmacist.receive_message({
                "sender_id": "orchestrator_trigger",
                "sender_role": "orchestrator",
                "content": review_request_content,
                "patient_id": patient_id
            })
            
            pharma_resp_status = pharmacist_response.get('content', {}).get('review_result', {}).get('status', 'unknown')
            logger.info(f"收到药剂师审核响应 (Patient: {patient_id})。Status: {pharma_resp_status}")
            return pharmacist_response
        except Exception as e:
            logger.error(f"触发药剂师处方审核时失败 (Patient: {patient_id}): {e}", exc_info=True)
            return {"status": "error", "content": {"review_result": {"status": "error", "message": f"触发药剂师审核时出错: {e}"}}}

    def process_consultation(self, patient_name: str, patient_age: int, symptoms: List[str], 
                            medical_history: Optional[List[str]] = None, 
                            additional_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """非Web场景的咨询处理方法（简化版）"""
        logger.warning("调用 process_consultation (非Web场景)，此方法当前为简化/非交互式实现，未与最新Web状态管理同步。")
        # 这个代码也有bug
        return {"status": "error", "message": "非Web场景的 process_consultation 未完全实现交互式状态管理逻辑。"}
