# agents/receptionist.py

import logging
import json
import re # Used for phone extraction
from typing import Dict, List, Any, Optional
from .base_agent import BaseAgent
try:
    from utils.llm_service import LLMService
    from utils.memory_system import MemorySystem
except ImportError as e:
    logging.error(f"ReceptionistAgent failed to import dependencies: {e}", exc_info=True)
    LLMService = None # type: ignore
    MemorySystem = None # type: ignore

logger = logging.getLogger("Hospital-MultiAgent-System")

VALID_DEPARTMENTS = ["内科", "外科", "儿科", "妇产科", "皮肤科", "眼科", "耳鼻喉科", "神经科", "心血管科", "消化内科", "呼吸内科", "骨科", "泌尿外科", "肿瘤科", "急诊科", "全科"]
DEFAULT_DEPARTMENT = "内科"
DEFAULT_PRIORITY = "normal"
PRIORITY_LEVELS = ["normal", "priority", "urgent"]
MAX_CHAT_TURNS = 3

STAGE_INTENT = "reception_intent_recognition"
STAGE_ASKING_IDENTITY = "reception_asking_identity"
STAGE_GUIDING = "reception_guiding_input"
STAGE_TRIAGE = "reception_ready_for_triage"
STAGE_COMPLETED = "reception_completed"
STAGE_CHATTING = "reception_chatting"
STAGE_CHAT_ENDED = "reception_chat_ended"
STAGE_CLARIFICATION = "reception_clarification"
STAGE_ERROR = "reception_error_handling"


class ReceptionistAgent(BaseAgent):
    """前台接待智能体 (支持多轮交互、身份识别和意图识别)"""

    def __init__(self, name: str = "前台接待员", role: str = "receptionist", memory_system: Optional[MemorySystem] = None, llm_service: Optional[LLMService] = None):
        super().__init__(name=name, role=role, memory_system=memory_system)
        self.llm_service = llm_service
        if not self.llm_service:
            logger.warning(f"接待员 {name}: LLM 服务未提供，意图识别和分诊功能将受限。")
        if not self.memory_system:
             logger.error(f"接待员 {name}: MemorySystem 未提供，无法管理多轮对话状态。")
        # 新增的默认闲聊过多回复
        self.off_topic_response = "您交流过多和看诊无关的话题，请描述您的具体症状，或明天再来沟通。我们需要给其他病人留出更多时间，谢谢理解。"
        logger.info(f"前台接待智能体 {name} 初始化完成")

    def _determine_intent_and_extract(self, user_message: str, patient_id: str, context: Optional[Dict]=None) -> Dict:
        if not self.llm_service:
             logger.error(f"无法进行意图识别 (Patient {patient_id})：LLM 服务不可用")
             return {"intent": "error", "message": "LLM 服务不可用"}
        history_summary = ""
        if context and context.get("conversation_snippets"):
             snippets_to_use = context["conversation_snippets"][-min(len(context["conversation_snippets"]), 4):]
             history_summary = "\n\n最近对话片段:\n" + "\n".join(snippets_to_use)
        prompt = f"""你是一个医院接待AI，需要判断用户的意图。

{history_summary}

用户最新消息: "{user_message}"

请分析用户最新消息的主要意图，并判断是否提供了足够的医疗信息（至少一个明确症状）。
可能的意图分类:
- "medical_inquiry": 用户在描述症状或健康问题。
- "general_chat": 闲聊、问候、询问非医疗信息、表达感谢等。
- "seeking_specific_doctor": 明确表示想找某位医生。
- "providing_identity": 用户在提供手机号或说明是否复诊 (可能是对你问题的回复)。
- "asking_guidance": 用户不确定如何描述，寻求引导。
- "unclear": 意图不明。

请严格按照以下JSON格式返回结果:
{{
  "intent": "...",
  "has_sufficient_medical_info": true/false,
  "extracted_symptoms": ["..."]
}}
如果意图是 "providing_identity"， "has_sufficient_medical_info" 和 "extracted_symptoms" 可能为 false/[]。
"""
        try:
            response_str = self.llm_service.generate_response(prompt=prompt, system_message="你是一个意图识别助手，请分析用户输入并以JSON格式返回结果。", temperature=0.1, max_tokens=200)
            logger.debug(f"意图识别LLM响应 (Patient {patient_id}): {response_str}")
            json_part = response_str.strip()
            match = re.search(r'\{.*\}', json_part, re.DOTALL)
            if match: json_part = match.group(0)
            result = json.loads(json_part)
            result["intent"] = result.get("intent", "unclear")
            result["has_sufficient_medical_info"] = bool(result.get("has_sufficient_medical_info", False))
            result["extracted_symptoms"] = result.get("extracted_symptoms", []) if isinstance(result.get("extracted_symptoms"), list) else []
            logger.info(f"意图识别结果 (Patient {patient_id}): Intent={result['intent']}, SufficientInfo={result['has_sufficient_medical_info']}, Symptoms={result['extracted_symptoms']}")
            return result
        except (json.JSONDecodeError, Exception) as e:
             logger.error(f"意图识别LLM调用或解析失败 (Patient {patient_id}): {e}", exc_info=True)
             return {"intent": "error", "message": f"意图识别失败: {e}"}

    def _extract_identity_info(self, message: str) -> Dict[str, Any]:
        phone_match = re.search(r'1[3-9]\d{9}', message)
        phone = phone_match.group(0) if phone_match else None
        is_return = None
        if any(keyword in message for keyword in ["复诊", "以前来过", "之前看过"]): is_return = True
        elif any(keyword in message for keyword in ["初诊", "第一次", "没来过"]): is_return = False
        elif is_return is None and any(keyword in message for keyword in ["是的", "是啊", "对"]): is_return = True
        elif is_return is None and any(keyword in message for keyword in ["不是", "没有"]): is_return = False
        extracted_symptoms = []
        symptom_text = message
        if phone: symptom_text = symptom_text.replace(phone, "")
        identity_phrases = ["手机号是", "号码是", "复诊", "初诊", "是的", "不是", "以前来过", "第一次", "没有", "对"]
        for phrase in identity_phrases: symptom_text = symptom_text.replace(phrase, "")
        possible_symptoms = re.split(r'[，。；、？！,.!?\s]+', symptom_text.strip())
        extracted_symptoms = [s.strip() for s in possible_symptoms if s.strip() and len(s.strip()) > 1 and s.strip() not in ["我", "你好", "谢谢"]]
        result = {"phone": phone,"is_return_visit_indicated": is_return,"additional_symptoms": extracted_symptoms}
        logger.debug(f"Extracted identity info: {result}")
        return result

    def _triage_with_llm(self, symptoms: List[str], patient_age: Optional[int], medical_history: List[str], is_return_visit: bool, previous_diagnosis: Optional[Dict]) -> Dict:
        if not self.llm_service:
             logger.error("无法进行分诊：LLM 服务不可用")
             return {"status": "error", "message": "LLM服务不可用，无法分诊", "department": DEFAULT_DEPARTMENT, "priority": DEFAULT_PRIORITY, "reason": "系统错误"}
        symptoms_string = ", ".join(symptoms) if symptoms else "未提供明确症状"
        history_string = ", ".join(medical_history) if medical_history else "无"
        return_visit_info = ""
        if is_return_visit:
             return_visit_info = "\n患者为复诊。"
             if previous_diagnosis and isinstance(previous_diagnosis, dict):
                 prev_cond = previous_diagnosis.get('condition', '未记录')
                 return_visit_info += f" 上次诊断可能与 {prev_cond} 相关。"
             else: return_visit_info += " (无上次具体诊断信息)"
        prompt = f"""你是一位经验丰富的医院分诊接待员。请根据以下患者信息，推荐最合适的就诊科室，并评估紧急程度（普通、优先、紧急）。

患者信息：
年龄：{patient_age if patient_age else '未知'}
主诉症状：{symptoms_string}
过往病史：{history_string}{return_visit_info}

请严格按照以下 JSON 格式返回结果:
{{
  "department": "推荐的科室名称 (从 {', '.join(VALID_DEPARTMENTS)} 中选择)",
  "priority": "紧急程度 ('normal', 'priority', 'urgent')",
  "reason": "推荐科室和判断紧急程度的简要理由"
}}
如果信息不足，推荐 "{DEFAULT_DEPARTMENT}" 和 "{DEFAULT_PRIORITY}"。非常紧急的情况（如严重外伤、呼吸困难、胸痛）推荐 "急诊科" 和 "urgent"。
"""
        try:
            llm_response_str = self.llm_service.generate_response(prompt=prompt, system_message="你是一位专业的医院分诊助手，请仔细分析信息并给出结构化JSON输出。", temperature=0.2, max_tokens=200)
            logger.debug(f"分诊LLM响应: {llm_response_str}")
            json_part = llm_response_str.strip()
            match = re.search(r'\{.*\}', json_part, re.DOTALL)
            if match: json_part = match.group(0)
            triage_result = json.loads(json_part)
            validated_result = {"status": "success","department": DEFAULT_DEPARTMENT,"priority": DEFAULT_PRIORITY,"reason": triage_result.get("reason", "LLM未提供理由。")}
            rec_dept = triage_result.get("department")
            if rec_dept and isinstance(rec_dept, str) and rec_dept in VALID_DEPARTMENTS: validated_result["department"] = rec_dept
            rec_prio = triage_result.get("priority")
            if rec_prio and isinstance(rec_prio, str) and rec_prio in PRIORITY_LEVELS: validated_result["priority"] = rec_prio
            logger.info(f"分诊结果: 科室={validated_result['department']}, 优先级={validated_result['priority']}")
            return validated_result
        except (json.JSONDecodeError, Exception) as e:
             logger.error(f"分诊LLM调用或解析失败: {e}", exc_info=True)
             return {"status": "error", "message": f"智能分诊失败: {e}", "department": DEFAULT_DEPARTMENT, "priority": DEFAULT_PRIORITY, "reason": "系统错误"}

    def _process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        sender_id = message.get("sender_id", "unknown")
        if not self.llm_service or not self.memory_system:
            logger.error("接待员无法处理请求：缺少 LLM 或 MemorySystem 服务。")
            return self.send_message(sender_id, {"status": "error", "message": "接待员内部服务错误，无法处理请求。"})

        user_message = ""; patient_id = None; consultation_id = None; context = None
        request_type = next((key for key in ["reception_request", "followup_query", "general_query"] if key in content), None)

        if request_type:
            request_data = content[request_type]
            patient_id = request_data.get("patient_id")
            consultation_id = request_data.get("consultation_id") or request_data.get("context_id")
            user_message = request_data.get("raw_message") or request_data.get("query") or ""
            if not consultation_id: 
                logger.error(f"请求类型 '{request_type}' 缺少 consultation_id/context_id")
                return self.send_message(sender_id, {"status": "error", "message": "内部错误：缺少会话标识。"})
            context = self.memory_system.get_consultation_context(consultation_id)
            if not context:
                if request_type == "reception_request":
                    logger.info(f"为咨询 {consultation_id} (Patient: {patient_id}) 创建新上下文")
                    context = {"patient_id": patient_id,"consultation_id": consultation_id,"stage": STAGE_INTENT,"chat_turns": 0,"conversation_snippets": [],"patient_info_from_web": request_data,"extracted_symptoms": request_data.get("symptoms", []),"guidance_given": False,"identity_asked": False,"identity_confirmed": False,"is_return_visit": None,"phone_provided": None}
                    self.memory_system.save_consultation_context(consultation_id, context)
                else: 
                    logger.error(f"找不到咨询上下文 {consultation_id} 用于后续消息")
                    return self.send_message(sender_id, {"status": "error", "message": f"会话已过期或无效 (ID: {consultation_id})"})
            else: 
                logger.info(f"找到现有上下文 {consultation_id}, 当前阶段: {context.get('stage')}")
                patient_id = context.get("patient_id", patient_id)
        else: 
            logger.warning(f"接待员收到未知类型的消息: {list(content.keys())}")
            return self.send_message(sender_id, {"status": "unhandled", "message": "接待员无法处理此请求类型。"})

        if not user_message or not patient_id: 
            logger.error(f"处理失败：缺少用户信息或消息内容 (Patient: {patient_id}, Msg: '{user_message[:20]}...')")
            return self.send_message(sender_id, {"status": "error", "message": "请求缺少用户信息或消息内容。"})

        context.setdefault("conversation_snippets", []).append(f"User: {user_message}")
        context["conversation_snippets"] = context["conversation_snippets"][-6:]
        self.memory_system.add_conversation_entry(context["patient_id"], "patient", user_message, metadata={"consultation_id": consultation_id, "agent_role": self.role})

        current_stage = context.get("stage", STAGE_INTENT)
        response_message = "抱歉，我暂时无法处理您的请求，请稍后再试。"
        next_stage = current_stage
        reception_result_data = None
        should_end_reception = False
        execute_triage = False

        if current_stage == STAGE_ASKING_IDENTITY:
            logger.info(f"处理用户对身份问题的回复 (Consultation: {consultation_id})")
            identity_info = self._extract_identity_info(user_message)
            phone = identity_info.get("phone")
            is_return_indicated = identity_info.get("is_return_visit_indicated")
            additional_symptoms = identity_info.get("additional_symptoms", [])
            context["phone_provided"] = phone
            found_patient_id = None
            if phone: found_patient_id = self.memory_system.find_patient_by_phone(phone)
            if found_patient_id:
                logger.info(f"找到匹配手机号的患者: {found_patient_id}。更新上下文。")
                context["patient_id"] = found_patient_id
                patient_id = found_patient_id
                context["identity_confirmed"] = True
                context["is_return_visit"] = False if is_return_indicated is False else True
                self.memory_system.add_or_update_patient_info(patient_id, {"phone": phone, "last_web_consultation_id": consultation_id})
            else:
                logger.info(f"未找到匹配手机号的患者，或未提供手机号。将使用当前ID: {patient_id}")
                context["identity_confirmed"] = False
                context["is_return_visit"] = True if is_return_indicated is True else False
                if phone: self.memory_system.add_or_update_patient_info(patient_id, {"phone": phone, "source": "web", "first_consultation_id": consultation_id})
            current_symptoms = set(context.get("extracted_symptoms", []))
            current_symptoms.update(additional_symptoms)
            context["extracted_symptoms"] = list(s for s in current_symptoms if s)
            if context["extracted_symptoms"] and context["extracted_symptoms"] != ["用户描述不清晰"]: 
                logger.info(f"身份信息处理完毕，症状充分，准备分诊 (Patient: {patient_id})")
                execute_triage = True
                next_stage = STAGE_TRIAGE
            else: 
                logger.info(f"身份信息处理完毕，但症状仍不足，需要引导 (Patient: {patient_id})")
                response_message = "谢谢您的信息。为了能准确地为您分诊，请您再尽量详细地描述一下您的症状，例如主要不适是什么？持续多久了？"
                next_stage = STAGE_GUIDING
                context["guidance_given"] = True
        else:
            intent_result = self._determine_intent_and_extract(user_message, patient_id, context)
            intent = intent_result.get("intent", "error")
            current_symptoms = set(context.get("extracted_symptoms", []))
            current_symptoms.update(intent_result.get("extracted_symptoms", []))
            context["extracted_symptoms"] = list(s for s in current_symptoms if s)
            if intent in ["general_chat", "seeking_specific_doctor"]:
                # 计数闲聊或者非诊疗相关对话的轮次
                context["off_topic_turns"] = context.get("off_topic_turns", 0) + 1
                context["chat_turns"] = context.get("chat_turns", 0) + 1
                logger.info(f"处理闲聊/找医生意图，当前轮次: {context['chat_turns']}，与诊断无关对话轮次: {context['off_topic_turns']}")
                
                # 检查是否超过了闲聊的最大轮数 - 注意这里是 >= 而不是 >
                if context["off_topic_turns"] >= MAX_CHAT_TURNS:
                    # 超过等于3轮闲聊，返回标准回复
                    logger.info(f"用户闲聊已达{MAX_CHAT_TURNS}轮，返回标准回复 (Patient: {patient_id})")
                    response_message = self.off_topic_response
                    next_stage = STAGE_CHAT_ENDED
                elif context["chat_turns"] <= MAX_CHAT_TURNS:
                    chat_prompt = f"""你是一个专业、有礼貌的医院接待员。用户刚才说："{user_message}"。请给出一个简洁、专业、乐于助人但【绝对不涉及】具体医疗建议或诊断的回复。如果是找特定医生，请礼貌地告知用户需要先描述症状以便系统分诊安排，我们无法直接指定医生。回复请少于50字。"""
                    try: 
                        response_message = self.llm_service.generate_response(chat_prompt, temperature=0.6, max_tokens=100)
                    except Exception as llm_err: 
                        logger.error(f"生成闲聊回复失败: {llm_err}")
                        response_message = "好的，我知道了。如果您有身体不适，请告诉我您的症状。"
                    next_stage = STAGE_CHATTING
                else: 
                    response_message = f"非常抱歉，我们已经聊了几句了。如果您有身体不适需要咨询，请详细描述您的症状，否则我需要优先处理其他患者的请求。"
                    next_stage = STAGE_CHAT_ENDED
            elif intent == "medical_inquiry" or (intent == "providing_identity" and not context.get("identity_asked")):
                if not context.get("identity_asked"): 
                    logger.info(f"识别到医疗意图或提前提供身份，准备询问/确认身份信息 (Patient: {patient_id})")
                    response_message = "了解您身体不适。为了更好地帮助您（特别是如果您之前来过），请问您的手机号码是多少？这次是复诊吗？"
                    context["identity_asked"] = True
                    next_stage = STAGE_ASKING_IDENTITY
                else:
                    if context["extracted_symptoms"] and context["extracted_symptoms"] != ["用户描述不清晰"]: 
                        logger.info("已有身份信息，且当前消息补充了足够症状，准备分诊。")
                        execute_triage = True
                        next_stage = STAGE_TRIAGE
                    elif not context.get("guidance_given"): 
                        logger.info(f"已有身份信息，但信息仍不足，提供引导 (Patient: {patient_id})")
                        response_message = """谢谢。为了能准确地为您分诊，请您尽量详细地描述一下您的症状，例如：
- 主要不适是什么？（如：头痛、咳嗽、腹泻）
- 这种不适持续多久了？
- 有没有其他伴随症状？（如：发烧、乏力、恶心）"""
                        next_stage = STAGE_GUIDING
                        context["guidance_given"] = True
                    else: 
                        response_message = "抱歉，我仍然需要您描述一下具体哪里不舒服才能继续。请告诉我您的主要症状。"
                        next_stage = STAGE_GUIDING
            elif intent == "providing_identity" and context.get("identity_asked"):
                logger.warning(f"User provided identity info again? Re-processing identity. (Consultation: {consultation_id})")
                identity_info = self._extract_identity_info(user_message)  # Process again
                # ... potentially repeat logic from STAGE_ASKING_IDENTITY block ...
                if context["extracted_symptoms"] and context["extracted_symptoms"] != ["用户描述不清晰"]: 
                    execute_triage = True
                    next_stage = STAGE_TRIAGE
                else: 
                    response_message = "谢谢您再次提供信息。请问您具体哪里不舒服？"
                    next_stage = STAGE_GUIDING
            elif intent in ["asking_guidance", "unclear"]:
                logger.info(f"用户意图不清或寻求引导 (Patient: {patient_id})")
                if not context.get("identity_asked") and not context.get("extracted_symptoms"): 
                    response_message = "您好，请问您哪里不舒服？为了更好地帮助您，也请告知您的手机号以及是否复诊。"
                    context["identity_asked"] = True
                    next_stage = STAGE_ASKING_IDENTITY
                else: 
                    response_message = "嗯，请问您具体哪里不舒服呢？或者您想咨询什么问题？请尽量详细描述，以便我能更好地帮助您。"
                    next_stage = STAGE_CLARIFICATION
            elif intent == "error": 
                response_message = f"抱歉，系统在理解您意图的时候好像出了点问题 ({intent_result.get('message')})。您能换种方式再说一遍吗？或者直接告诉我您的症状？"
                next_stage = STAGE_ERROR

        if execute_triage:
            logger.info(f"执行分诊逻辑 (Patient: {patient_id})")
            triage_input_symptoms = context.get("extracted_symptoms", [])
            if not triage_input_symptoms or triage_input_symptoms == ["用户描述不清晰"]: 
                response_message = "抱歉，我还是没能获取到您的具体症状描述。请告诉我哪里不舒服。"
                next_stage = STAGE_GUIDING
                context["guidance_given"] = False
            else:
                patient_info_for_llm = {}
                patient_db_info = None
                if context.get("identity_confirmed"): 
                    patient_db_info = self.memory_system.get_patient_info(patient_id)
                    patient_info_for_llm = patient_db_info.copy() if patient_db_info else {}
                else: 
                    patient_info_for_llm = context.get("patient_info_from_web", {}).copy()
                    patient_info_for_llm["name"] = patient_info_for_llm.get("patient_name", "网页用户")
                medical_history_list = []
                if context.get("identity_confirmed"):
                    summaries = self.memory_system.get_consolidated_long_term_memories(patient_id, limit=2)
                    medical_history_list = [f"过往诊断摘要: {s.get('summary',{}).get('key_diagnoses','N/A')}" for s in summaries]
                    medical_history_list = medical_history_list or ["有就诊记录但无摘要"]
                else: 
                    medical_history_list = context.get("patient_info_from_web", {}).get("medical_history", [])
                triage_llm_result = self._triage_with_llm(symptoms=triage_input_symptoms, patient_age=patient_info_for_llm.get("age"), medical_history=medical_history_list, is_return_visit=context.get("is_return_visit", False), previous_diagnosis=None)
                if triage_llm_result.get("status") == "success":
                    determined_department = triage_llm_result["department"]
                    priority = triage_llm_result["priority"]
                    reason = triage_llm_result["reason"]
                    priority_text_map = {"normal": "普通", "priority": "优先", "urgent": "紧急"}
                    priority_text = priority_text_map.get(priority, "普通")
                    visit_status_msg = "（已记录为复诊）" if context.get("is_return_visit") else "（已记录为初诊）"
                    response_message = f"好的，感谢您的信息{visit_status_msg}。根据您的描述 ({', '.join(triage_input_symptoms)}) 和初步分析，建议您挂 [{determined_department}] 科。系统评估的就诊优先级为：[{priority_text}]。正在为您安排后续流程... (理由: {reason})"
                    next_stage = STAGE_COMPLETED
                    should_end_reception = True
                    reception_result_data = {
                        "status": "success",
                        "patient_id": patient_id,
                        "department": determined_department,
                        "priority": priority,
                        "notes": f"分诊完成。身份确认: {context.get('identity_confirmed')}, 是否复诊: {context.get('is_return_visit')}, 电话提供: {'是' if context.get('phone_provided') else '否'}. LLM理由: {reason}",
                        "message": response_message,
                        "patient_info_final": patient_db_info or patient_info_for_llm
                    }
                else: 
                    response_message = f"抱歉，在为您进行智能分诊时遇到问题 ({triage_llm_result.get('message')})。我们将为您安排到 [{DEFAULT_DEPARTMENT}]，请向医生详细说明情况。"
                    next_stage = STAGE_COMPLETED
                    should_end_reception = True
                    reception_result_data = {
                        "status": "success",
                        "patient_id": patient_id,
                        "department": DEFAULT_DEPARTMENT,
                        "priority": DEFAULT_PRIORITY,
                        "notes": f"分诊完成。LLM智能分诊失败: {triage_llm_result.get('message')}. 使用默认科室。",
                        "message": response_message,
                        "patient_info_final": patient_db_info or patient_info_for_llm
                    }

        if execute_triage and reception_result_data: 
            response_message = reception_result_data.get("message", response_message)

        context["stage"] = next_stage
        context.setdefault("conversation_snippets", []).append(f"Receptionist: {response_message}")
        context["conversation_snippets"] = context["conversation_snippets"][-6:]
        self.memory_system.update_consultation_context(consultation_id, context)

        final_response_content = {
            "status": STAGE_COMPLETED if should_end_reception else "in_progress",
            "message": response_message,
            "next_stage": next_stage,
            "reception_result": reception_result_data
        }
        self.memory_system.add_conversation_entry(context["patient_id"], self.role, response_message, metadata={"consultation_id": consultation_id, "next_stage": next_stage})
        return self.send_message(sender_id, final_response_content)
