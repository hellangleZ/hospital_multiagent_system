#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
医生智能体，负责诊断患者并开具处方 (状态管理依赖MemorySystem)
"""

import logging
import json
import uuid
from typing import Dict, List, Any, Optional
from .base_agent import BaseAgent
try:
    from utils.llm_service import LLMService
    from utils.memory_system import MemorySystem
except ImportError as e:
     logging.error(f"导入依赖失败: {e}")
     LLMService = None
     MemorySystem = None

logger = logging.getLogger("Hospital-MultiAgent-System")

class DoctorAgent(BaseAgent):
    """医生智能体"""

    def __init__(self, name: str = "主治医生", specialty: str = "general", memory_system: Optional[MemorySystem] = None, llm_service: Optional[LLMService] = None):
        super().__init__(name=name, role="doctor", memory_system=memory_system)
        self.specialty = specialty
        self.llm_service = llm_service
        if not self.llm_service: logger.error(f"医生 {name}: LLM 服务未提供。")
        if not self.memory_system: logger.error(f"医生 {name}: MemorySystem 未提供。")
        logger.info(f"医生智能体 {name} ({specialty}) 初始化完成")

    def _process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理接收到的消息（通常来自Orchestrator）"""
        content = message.get("content", {})
        sender_id = message.get("sender_id", "unknown")

        if not self.llm_service or not self.memory_system:
             logger.error(f"医生 {self.name} 无法处理请求，缺少 LLM 或 MemorySystem。")
             return self.send_message(sender_id, {"status": "error", "message": "内部服务错误，无法处理诊断请求。"})

        if "diagnose_request" in content:
            return self._handle_diagnosis_request(message)
        elif "patient_response" in content:
            return self._handle_patient_response(message)
        elif "prescription_request" in content:
             logger.info(f"医生 {self.name} 收到独立的处方请求。")
             return self._handle_prescription_request(message)
        else:
            logger.warning(f"医生 {self.name} 收到未知类型的消息: {list(content.keys())}")
            return self.send_message(sender_id, {"status": "unhandled", "message": f"医生无法处理此请求类型。"})

    # --- 内部处理方法 ---

    def _handle_diagnosis_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理诊断请求，启动交互式问诊"""
        content = message.get("content", {})
        request = content.get("diagnose_request", {})
        patient_id = request.get("patient_id")
        # --- 关键修改：获取 consultation_id ---
        consultation_id = request.get("consultation_id")
        # ------------------------------------
        sender_id = message.get("sender_id", "unknown")

        if not patient_id or not consultation_id: # 确保两个ID都存在
            logger.error("诊断请求缺少 patient_id 或 consultation_id")
            return self.send_message(sender_id, {"status": "error", "message": "诊断请求缺少必要ID"})

        symptoms = request.get("symptoms", [])
        medical_history = request.get("medical_history", [])
        department = request.get("department", self.specialty)
        is_return_visit = request.get("is_return_visit", False)
        previous_diagnosis = request.get("previous_diagnosis")
        reception_notes = request.get("reception_notes", "") # 获取接待员备注

        logger.info(f"医生 {self.name} 开始处理患者 {patient_id} 的诊断请求 (Consultation: {consultation_id})。复诊: {is_return_visit}")

        initial_context = {
            "patient_id": patient_id,
            "consultation_id": consultation_id, # 在上下文中也存一份
            "initial_symptoms": symptoms.copy(),
            "medical_history": medical_history.copy(),
            "department": department,
            "current_symptoms": symptoms.copy(),
            "questions_asked": [],
            "patient_responses": [],
            "confidence": 0.3,
            "stage": "information_gathering", # 设置医生的阶段
            "is_return_visit": is_return_visit,
            "previous_diagnosis": previous_diagnosis,
            "reception_notes": reception_notes # 保存接待员备注
        }

        try:
            first_question = self._generate_next_question(initial_context)
            initial_context["questions_asked"].append(first_question)

            # --- 关键修改：使用 consultation_id 作为 key 保存上下文 ---
            self.memory_system.save_consultation_context(consultation_id, initial_context)
            # -----------------------------------------------

            response_content = {
                "status": "in_consultation",
                "requires_patient_input": True,
                "question": first_question,
                # --- 关键修改：传递正确的 consultation_id 作为 context_id ---
                "context_id": consultation_id,
                # ----------------------------------------------------
                "patient_id": patient_id
            }
            # 记录到患者记忆和对话历史
            self.memory_system.add_patient_memory(patient_id, "consultation_started_by_doctor",
                                                  {"context_id": consultation_id, "symptoms": symptoms, "department": department},
                                                  metadata={"agent_id": self.id})
            self.memory_system.add_conversation_entry(patient_id, self.role, first_question,
                                                       metadata={"agent_id": self.id, "consultation_id": consultation_id}) # 使用 consultation_id

            return self.send_message(sender_id, response_content)

        except Exception as e:
            logger.error(f"为患者 {patient_id} 生成首个问题时出错 (Consultation: {consultation_id}): {e}", exc_info=True)
            return self.send_message(sender_id, {"status": "error", "message": f"开始问诊时出错: {e}"})


    def _handle_patient_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理患者的回答，推进问诊流程"""
        content = message.get("content", {})
        response_data = content.get("patient_response", {})
        patient_id = response_data.get("patient_id")
        answer = response_data.get("answer", "")
        # --- 关键修改：使用 context_id (它现在等于 consultation_id) ---
        context_id = response_data.get("context_id")
        # ----------------------------------------------------
        sender_id = message.get("sender_id", "unknown")

        if not context_id or not patient_id:
            logger.error("患者回复消息缺少 context_id 或 patient_id")
            return self.send_message(sender_id, {"status": "error", "message": "患者回复缺少必要ID"})
        if not answer:
             logger.warning(f"收到来自 patient {patient_id} 的空回复 (Context: {context_id})")
             # 可以选择追问或忽略，这里简单返回错误提示
             return self.send_message(sender_id, {"status": "error", "message": "收到的回复内容为空，请重新输入。"})

        current_context = self.memory_system.get_consultation_context(context_id)
        if not current_context:
            logger.error(f"处理患者回复失败：找不到或问诊已过期 (context_id: {context_id})")
            return self.send_message(sender_id, {"status": "error", "message": f"会话已过期或无效 (ID: {context_id})"})

        logger.info(f"医生 {self.name} 收到患者 {patient_id} 对问题 (Context: {context_id}) 的回答: '{answer[:50]}...'")
        self.memory_system.add_conversation_entry(patient_id, "patient", answer, metadata={"consultation_id": context_id})

        try:
            current_context.setdefault("patient_responses", []).append(answer) # 确保列表存在
            last_question = current_context.get("questions_asked", [])[-1] if current_context.get("questions_asked") else "无先前问题"
            analysis_result = self._analyze_patient_response(last_question, answer)

            new_symptoms = analysis_result.get("new_symptoms", [])
            if new_symptoms:
                current_symptoms_set = set(current_context.get("current_symptoms", []))
                current_symptoms_set.update(new_symptoms)
                current_context["current_symptoms"] = list(current_symptoms_set) # 更新症状列表

            current_context["confidence"] = min(1.0, current_context.get("confidence", 0.3) + analysis_result.get("confidence_delta", 0.0))
            # 可以存储 symptom_details 和 related_info
            current_context.setdefault("symptom_details", {}).update(analysis_result.get("symptom_details", {}))
            current_context.setdefault("related_info", {}).update(analysis_result.get("related_info", {}))


            logger.info(f"患者 {patient_id} 回答分析完成。当前症状: {current_context['current_symptoms']}. 置信度: {current_context['confidence']:.2f}")

            can_diagnose = self._can_make_diagnosis(current_context)

            if can_diagnose:
                 logger.info(f"医生 {self.name} 可以为患者 {patient_id} (Context: {context_id}) 做出诊断。")
                 final_diagnosis = self._generate_diagnosis_with_llm(
                     current_context["current_symptoms"],
                     current_context["medical_history"],
                     current_context["department"]
                 )
                 current_context["diagnosis"] = final_diagnosis
                 current_context["stage"] = "diagnosis_complete" # 更新阶段

                 response_content = {
                     "status": "diagnosis_complete",
                     "context_id": context_id,
                     "patient_id": patient_id,
                     "diagnosis_result": {
                         "status": "success",
                         "diagnosis": final_diagnosis,
                         "message": "感谢您的配合。根据您提供的信息，我已完成初步诊断。",
                         "explanation": final_diagnosis.get("explanation", ""),
                         "recommendations": final_diagnosis.get("recommendations", []),
                         "prescription": final_diagnosis.get("medications", []),
                         "follow_up": final_diagnosis.get("follow_up", "建议后续定期复查")
                     }
                 }
                 self.memory_system.add_patient_memory(patient_id, "diagnosis", final_diagnosis,
                                                       metadata={"agent_id": self.id, "consultation_id": context_id})
                 self.memory_system.delete_consultation_context(context_id) # 诊断完成，删除上下文
                 return self.send_message(sender_id, response_content)

            else:
                 logger.info(f"医生 {self.name} 需要向患者 {patient_id} (Context: {context_id}) 提出下一个问题。")
                 next_question = self._generate_next_question(current_context)
                 current_context.setdefault("questions_asked", []).append(next_question) # 确保列表存在

                 self.memory_system.update_consultation_context(context_id, current_context) # 更新上下文
                 self.memory_system.add_conversation_entry(patient_id, self.role, next_question,
                                                          metadata={"agent_id": self.id, "consultation_id": context_id})

                 response_content = {
                     "status": "in_consultation",
                     "requires_patient_input": True,
                     "question": next_question,
                     "context_id": context_id, # 继续传递
                     "patient_id": patient_id
                 }
                 return self.send_message(sender_id, response_content)

        except Exception as e:
             logger.error(f"处理患者 {patient_id} 回答 (Context: {context_id}) 时出错: {e}", exc_info=True)
             self.memory_system.delete_consultation_context(context_id) # 出错时也删除上下文
             return self.send_message(sender_id, {"status": "error", "message": f"处理您的回答时发生内部错误。"})


    def _handle_prescription_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
         """处理独立的开处方请求"""
         content = message.get("content", {})
         request = content.get("prescription_request", {})
         patient_id = request.get("patient_id")
         diagnosis = request.get("diagnosis", {})
         # --- 获取 consultation_id (如果存在) ---
         consultation_id = request.get("consultation_id")
         # --------------------------------------
         sender_id = message.get("sender_id", "unknown")

         if not patient_id or not diagnosis:
              return self.send_message(sender_id, {"status": "error", "message": "处方请求缺少 patient_id 或 diagnosis 信息"})

         logger.info(f"医生 {self.name} 收到为患者 {patient_id} 基于提供诊断开具处方的请求 (Consultation: {consultation_id or 'N/A'})")

         suggested_medications = diagnosis.get("medications", [])
         instructions = diagnosis.get("recommendations", ["遵医嘱"])
         follow_up = diagnosis.get("follow_up", "如有不适请复诊")
         diagnosis_condition = diagnosis.get("condition", "未在诊断中指定")

         prescription = {
             "diagnosis": diagnosis_condition,
             "medications": suggested_medications,
             "instructions": " ".join(instructions) if isinstance(instructions, list) else instructions,
             "notes": follow_up
         }

         # 记录处方信息，关联 consultation_id
         metadata_for_memory = {"agent_id": self.id, "based_on_diagnosis": diagnosis_condition}
         if consultation_id: metadata_for_memory["consultation_id"] = consultation_id
         self.memory_system.add_patient_memory(patient_id, "prescription_generated", prescription, metadata=metadata_for_memory)

         response_content = {
             "status": "prescription_ready",
             "prescription": prescription,
             "patient_id": patient_id,
             "consultation_id": consultation_id # 将 ID 传回
         }
         return self.send_message(sender_id, response_content)


    # --- LLM 调用和判断逻辑 (保持不变，因为它们接收 context) ---
    def _generate_next_question(self, context: Dict[str, Any]) -> str:
        # ... (代码不变)
        prompt = f"""作为一位专业医生，根据以下问诊上下文信息生成下一个有针对性的问题:
患者ID: {context.get('patient_id', 'N/A')}
初始症状: {', '.join(context.get('initial_symptoms', []))}
当前已知症状: {', '.join(context.get('current_symptoms', []))}
病史: {', '.join(context.get('medical_history', []))}
科室: {context.get('department', '未知')}
已问过的问题: {json.dumps(context.get('questions_asked', []), ensure_ascii=False)}
患者的回答: {json.dumps(context.get('patient_responses', []), ensure_ascii=False)}
当前诊断置信度: {context.get('confidence', 0.3):.2f}
是否复诊: {context.get('is_return_visit', False)}
{f"上次诊断: {json.dumps(context.get('previous_diagnosis'), ensure_ascii=False)}" if context.get('is_return_visit') and context.get('previous_diagnosis') else ""}
{f"接待员备注: {context.get('reception_notes', '')}" if context.get('reception_notes') else ""}

请生成一个专业、有针对性的问题，帮助进一步了解患者情况以提高诊断准确性。问题应该避免重复，并根据已知信息深入挖掘。

只返回问题文本本身，不要包含其他内容。
"""
        try:
            response = self.llm_service.generate_response(prompt=prompt, system_message="你是一位专业医生，正在进行交互式问诊。请提出精准、简洁的下一个问题。", temperature=0.6)
            return response
        except Exception as e:
            logger.error(f"生成下一个问诊问题时出错 (Patient: {context.get('patient_id')}): {str(e)}")
            return "能再详细描述一下您最不舒服的感觉吗？或者还有其他症状吗？" # Fallback

    def _analyze_patient_response(self, question: str, answer: str) -> Dict[str, Any]:
        # ... (代码不变)
        prompt = f"""作为专业医疗信息分析员，请分析患者对以下问题的回答，并提取关键信息:

医生的问题: "{question}"
患者的回答: "{answer}"

请严格以JSON格式返回分析结果，包含以下字段:
- "new_symptoms": 从回答中提取出的新症状列表 (List[str])。
- "symptom_details": 对已有症状的详细描述或确认 (Dict[str, str])。
- "negated_symptoms": 患者明确否认的症状列表 (List[str])。
- "related_info": 其他可能相关的非症状信息 (Dict[str, str])。
- "confidence_delta": 基于这个回答对诊断把握度的提升预估值 (float, 范围 0.0 到 0.2)。

如果无法提取某项信息，请使用空列表[]或空字典{{}}。确保JSON格式正确。
"""
        try:
            response = self.llm_service.generate_response(prompt=prompt, system_message="你是一个医疗信息提取和分析助手。请仔细分析医患对话并按要求输出JSON。", temperature=0.1, max_tokens=300)
            json_part = response.strip()
            if json_part.startswith("```json"): json_part = json_part[7:]
            if json_part.endswith("```"): json_part = json_part[:-3]
            json_part = json_part.strip()
            analysis = json.loads(json_part)
            analysis["new_symptoms"] = analysis.get("new_symptoms", [])
            analysis["symptom_details"] = analysis.get("symptom_details", {})
            analysis["negated_symptoms"] = analysis.get("negated_symptoms", [])
            analysis["related_info"] = analysis.get("related_info", {})
            analysis["confidence_delta"] = float(analysis.get("confidence_delta", 0.0))
            return analysis
        except (json.JSONDecodeError, ValueError, Exception) as e:
            logger.error(f"分析患者回答时出错: {str(e)}. Raw Response: {response if 'response' in locals() else 'N/A'}")
            return {"new_symptoms": [], "symptom_details": {}, "negated_symptoms": [], "related_info": {}, "confidence_delta": 0.0}


    def _can_make_diagnosis(self, context: Dict[str, Any]) -> bool:
        # ... (代码不变)
        confidence = context.get("confidence", 0.3); questions_asked_count = len(context.get("questions_asked", []))
        min_confidence = 0.75; max_questions = 5; min_questions_force_diag = 4
        if confidence >= min_confidence: logger.info(f"可以诊断：置信度 {confidence:.2f} >= {min_confidence}"); return True
        if questions_asked_count >= max_questions: logger.info(f"可以诊断：已达到最大问题数 {max_questions}"); return True
        if questions_asked_count >= min_questions_force_diag and confidence > 0.4: logger.info(f"可以诊断：问题数 {questions_asked_count} >= {min_questions_force_diag} 且置信度 {confidence:.2f} > 0.4"); return True
        logger.debug(f"不能诊断：置信度 {confidence:.2f}, 问题数 {questions_asked_count}"); return False


    def _generate_diagnosis_with_llm(self, symptoms: List[str], medical_history: List[str], department: str) -> Dict[str, Any]:
        """使用LLM生成诊断结果"""
        prompt = f"""作为专业医生，请根据以下信息生成诊断结果：
症状：{', '.join(symptoms) if symptoms else '未提供'}
病史：{', '.join(medical_history) if medical_history else '无'}
科室：{department}

请以JSON格式返回诊断结果，包含以下字段:
- "condition": 诊断结果
- "explanation": 诊断解释
- "severity": 严重程度
- "recommendations": 建议措施列表
- "medications": 药物列表，每项包含name, dosage, purpose
- "follow_up": 随访建议
- "differential_diagnosis": 鉴别诊断列表（可选）
- "diagnostic_tests": 建议检查列表（可选）

请确保JSON格式简洁且完整，避免过长的描述导致内容被截断。每个字段的值保持在50字以内，列表项不超过5个。
"""
        try:
            # 增加max_tokens以确保完整接收回复
            response = self.llm_service.generate_response(
                prompt=prompt, 
                system_message="你是一位资深医生，正在进行诊断。请给出专业、简洁且结构化的诊断结果（JSON格式）。", 
                temperature=0.3, 
                max_tokens=1000
            )
            
            # 提取JSON部分
            json_part = response.strip()
            if json_part.startswith("```json"): 
                json_part = json_part[7:]
            if json_part.endswith("```"): 
                json_part = json_part[:-3]
            json_part = json_part.strip()
            
            # 尝试解析JSON
            try:
                diagnosis = json.loads(json_part)
            except json.JSONDecodeError as json_err:
                # 处理JSON解析错误
                logger.error(f"JSON解析失败: {json_err}. 尝试修复...")
                
                # 尝试修复可能的不完整JSON
                if "diagnostic_tests" in json_part and json_err.msg.startswith("Unterminated string"):
                    # 如果是字符串截断的错误，尝试创建一个简化版本
                    logger.warning(f"检测到JSON截断，创建简化版本")
                    simple_diagnosis = {
                        "condition": self._extract_field(json_part, "condition") or "可能的消化系统疾病",
                        "explanation": self._extract_field(json_part, "explanation") or "根据症状判断",
                        "severity": self._extract_field(json_part, "severity") or "需要进一步检查",
                        "recommendations": self._extract_list(json_part, "recommendations") or ["请遵医嘱"],
                        "medications": [],  # 简化版不包含药物
                        "follow_up": "请在获得完整检查结果后再次就诊",
                        "differential_diagnosis": self._extract_list(json_part, "differential_diagnosis") or [],
                        "diagnostic_tests": ["建议进行相关检查确认诊断"]
                    }
                    diagnosis = simple_diagnosis
                    logger.info("成功创建简化版诊断结果")
                else:
                    # 其他类型的JSON错误，使用默认诊断
                    raise
            
            # 确保所有字段存在，避免后续处理时出错
            diagnosis["condition"] = diagnosis.get("condition", "无法明确诊断")
            diagnosis["explanation"] = diagnosis.get("explanation", "未能生成完整解释。") 
            diagnosis["severity"] = diagnosis.get("severity", "未知") 
            diagnosis["recommendations"] = diagnosis.get("recommendations", [])
            diagnosis["medications"] = diagnosis.get("medications", [])
            diagnosis["follow_up"] = diagnosis.get("follow_up", "请遵医嘱，如有不适及时复诊。")
            diagnosis["differential_diagnosis"] = diagnosis.get("differential_diagnosis", [])
            diagnosis["diagnostic_tests"] = diagnosis.get("diagnostic_tests", [])
            
            # 确保所有列表字段确实是列表类型
            for list_field in ["recommendations", "medications", "differential_diagnosis", "diagnostic_tests"]:
                if not isinstance(diagnosis.get(list_field), list):
                    diagnosis[list_field] = [str(diagnosis.get(list_field))] if diagnosis.get(list_field) else []
            
            logger.info(f"为症状 '{', '.join(symptoms)}' 生成诊断结果：{diagnosis.get('condition')}")
            return diagnosis
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"生成诊断结果时出错: {str(e)}. Raw Response: {response if 'response' in locals() else 'N/A'}")
            return {
                "condition": "诊断生成失败", 
                "explanation": f"系统错误: {str(e)}", 
                "differential_diagnosis": [], 
                "severity": "未知", 
                "recommendations": ["请咨询人类医生。"], 
                "medications": [], 
                "follow_up": "请立即联系医生。", 
                "diagnostic_tests": []
            }
    
    def _extract_field(self, json_text: str, field_name: str) -> str:
        """从部分JSON文本中提取单个字段的值"""
        try:
            import re
            pattern = f'"{field_name}"\\s*:\\s*"([^"]*)"'
            match = re.search(pattern, json_text)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"提取字段 {field_name} 时出错: {e}")
            return None
    
    def _extract_list(self, json_text: str, field_name: str) -> List[str]:
        """从部分JSON文本中提取列表字段的值"""
        try:
            import re
            # 尝试匹配字段名后面的数组部分
            pattern = f'"{field_name}"\\s*:\\s*\\[(.*?)\\]'
            match = re.search(pattern, json_text, re.DOTALL)
            if not match:
                return None
                
            items_text = match.group(1).strip()
            if not items_text:
                return []
                
            # 提取数组中的所有字符串项
            items = []
            for item_match in re.finditer('"([^"]*)"', items_text):
                items.append(item_match.group(1))
            return items
        except Exception as e:
            logger.error(f"提取列表 {field_name} 时出错: {e}")
            return None