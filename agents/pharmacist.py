#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
药剂师智能体，负责处理处方审核、药物信息查询和相互作用检查
"""

import logging
import json
import re  # 用于从错误消息中提取信息
from typing import Dict, List, Any, Optional

# 导入 BaseAgent
from .base_agent import BaseAgent

# 导入依赖项，添加类型提示和错误处理
try:
    from utils.llm_service import LLMService
    from utils.memory_system import MemorySystem
except ImportError as e:
    logging.error(f"药剂师 Agent 导入依赖失败: {e}")
    LLMService = None
    MemorySystem = None

logger = logging.getLogger("Hospital-MultiAgent-System")

# --- Constants ---
VALID_DEPARTMENTS = [  # 这个列表可能药剂师也需要参考，或者从配置导入
    "内科", "外科", "儿科", "妇产科", "皮肤科", "眼科",
    "耳鼻喉科", "神经科", "心血管科", "消化内科", "呼吸内科",
    "骨科", "泌尿外科", "肿瘤科", "急诊科", "全科"
]


class PharmacistAgent(BaseAgent):
    """药剂师智能体"""
    
    def __init__(self, name: str = "药剂师", role: str = "pharmacist", memory_system=None, llm_service=None):
        super().__init__(name=name, role=role, memory_system=memory_system)
        self.llm_service = llm_service
        if not self.llm_service:
            logger.warning(f"药剂师 {name}: LLM 服务未提供。")
        logger.info(f"药剂师智能体 {name} 初始化完成")

    def process_message(self, message: str, session: dict) -> dict:
        """
        处理来自网页界面的对话消息
        
        Args:
            message: 患者发送的消息文本
            session: 当前会话状态
            
        Returns:
            dict: 包含回复消息和其他信息的字典
        """
        try:
            # 检查是否有待审核的处方
            if "prescription" not in session:
                return {
                    "message": "抱歉，我还没有收到需要审核的处方。"
                }
                
            prescription = session["prescription"]
            
            # 处方审核
            validation_result = self._validate_prescription_with_llm(prescription)
            
            # 分析用户的问题并提供相应的答复
            if "药" in message or "处方" in message or "用药" in message:
                if validation_result["valid"]:
                    # 获取每种药物的详细信息
                    drug_info_list = []
                    for med in prescription.get("medications", []):
                        drug_info = self._get_drug_info_with_llm(med["name"])
                        if drug_info:
                            drug_info_list.append(f"【{med['name']}】\n用法：{med['dosage']}，{med['frequency']}\n说明：{drug_info.get('description', '无')}\n注意事项：{drug_info.get('side_effects', '无')}")
                    
                    drug_instructions = "\n\n".join(drug_info_list)
                    
                    return {
                        "message": f"处方已通过审核，以下是详细的用药说明：\n\n{drug_instructions}\n\n" + \
                                 f"医嘱：{prescription.get('instructions', '请遵医嘱服用')}\n\n" + \
                                 f"随访建议：{prescription.get('notes', '请遵医嘱定期复查')}",
                        "prescription": prescription
                    }
                else:
                    issues = "、".join(validation_result["issues"])
                    return {
                        "message": f"处方审核发现以下问题：{issues}\n我需要与医生沟通修改处方。"
                    }
            
            # 药物相互作用咨询
            elif "相互作用" in message or "一起" in message:
                medications = [med["name"] for med in prescription.get("medications", [])]
                interactions = self._check_drug_interactions_with_llm(medications)
                
                if interactions:
                    interaction_text = []
                    for interaction in interactions:
                        drugs = interaction["drug_pair"]
                        interaction_text.append(f"{drugs[0]}与{drugs[1]}：{interaction['description']}")
                    return {
                        "message": "以下是药物相互作用的说明：\n" + "\n".join(interaction_text)
                    }
                else:
                    return {
                        "message": "目前没有发现处方中的药物之间存在明显的相互作用问题。"
                    }
            
            # 其他一般问题
            else:
                return {
                    "message": "您有任何关于药品使用的问题都可以问我。我可以为您解释：\n" + \
                             "1. 药品的具体用法用量\n" + \
                             "2. 药品的注意事项\n" + \
                             "3. 药品是否有相互作用\n" + \
                             "4. 其他用药相关的问题"
                }
                
        except Exception as e:
            logger.error(f"处理患者消息时出错: {str(e)}")
            return {
                "message": "抱歉，处理您的问题时出现了错误。请重新描述您的问题。"
            }

    def _process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        sender_id = message.get("sender_id", "unknown")

        if not self.llm_service:
            logger.error(f"药剂师 {self.name} 无法处理请求，缺少 LLM 服务。")
            return self.send_message(sender_id, {"status": "error", "message": "内部服务错误，无法处理药学请求。"})

        if "review_request" in content:
            return self._handle_review_request(message)
        elif "drug_info_request" in content:
            return self._handle_drug_info_request(message)
        elif "interaction_check" in content:
            return self._handle_interaction_check(message)
        elif "patient_query_about_prescription" in content:
            return self._handle_patient_prescription_query(message)
        else:
            logger.warning(f"药剂师 {self.name} 收到未知类型的消息: {list(content.keys())}")
            return self.send_message(sender_id, {"status": "unhandled", "message": "药剂师无法处理此请求类型。"})

    # --- 内部处理方法 ---

    def _handle_review_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        request = content.get("review_request", {})
        patient_id = request.get("patient_id")
        prescription = request.get("prescription", {})
        sender_id = message.get("sender_id", "unknown")
        diagnosis_info = request.get("diagnosis", {})  # 获取诊断信息
        
        if not patient_id or not prescription or not prescription.get("medications"):
            logger.error(f"处方审核请求无效 (Sender: {sender_id}): 缺少 patient_id 或处方/药物信息。")
            return self.send_message(sender_id, {
                "status": "error",
                "review_result": {
                    "status": "rejected",
                    "patient_id": patient_id,
                    "message": "处方审核请求缺少 patient_id 或有效的药物信息"
                }
            })
            
        logger.info(f"药剂师 {self.name} 正在审核患者 {patient_id} 的处方...")
        # --- 修改：传递诊断信息给审核函数 ---
        validation_result = self._validate_prescription_with_llm(prescription, patient_id, diagnosis_info)
        # ----------------------------------
        is_approved = validation_result.get("valid", False)
        final_prescription = prescription.copy()
        
        if self.memory_system:
            memory_data = {
                "prescription": prescription,
                "validation_result": validation_result,
                "is_approved": is_approved
            }
            self.memory_system.add_patient_memory(
                patient_id,
                "prescription_review",
                memory_data,
                metadata={"agent_id": self.id}
            )
            
        if is_approved:
            logger.info(f"患者 {patient_id} 的处方已通过审核")
            if validation_result.get("recommendations"):
                recs = "; ".join(validation_result["recommendations"])
                note_key = "pharmacist_notes"
                final_prescription[note_key] = final_prescription.get(note_key, "") + f"\n药剂师建议: {recs}"
            
            response_content = {
                "review_result": {
                    "status": "approved",
                    "patient_id": patient_id,
                    "prescription": final_prescription,
                    "notes": f"处方已审核通过。{validation_result.get('notes', '')}"
                }
            }
        else:
            issues = validation_result.get("issues", [])
            issue_text = "、".join(issues) if issues else "处方存在未明确的问题"
            logger.warning(f"患者 {patient_id} 的处方未通过审核: {issue_text}")
            response_content = {
                "review_result": {
                    "status": "rejected",
                    "patient_id": patient_id,
                    "issues": issues,
                    "warnings": validation_result.get("warnings", []),
                    "message": f"处方审核未通过: {issue_text}。{validation_result.get('notes', '')} 请医生复核或修改处方。"
                }
            }
        return self.send_message(sender_id, response_content)

    def _handle_drug_info_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        request = content.get("drug_info_request", {})
        drug_name = request.get("drug_name", "").strip()
        sender_id = message.get("sender_id", "unknown")
        
        if not drug_name:
            return self.send_message(sender_id, {"status": "error", "message": "药物信息请求缺少 drug_name"})
            
        logger.info(f"药剂师 {self.name} 收到查询药物 '{drug_name}' 信息的请求")
        drug_info = self._get_drug_info_with_llm(drug_name)
        
        if drug_info and not drug_info.get("error"):
            response_content = {
                "status": "info_provided",
                "drug_name": drug_name,
                "drug_info": drug_info,
                "message": f"已找到关于药物 {drug_name} 的信息。"
            }
        else:
            error_msg = drug_info.get("error", "未知错误")
            logger.warning(f"未能找到药物 '{drug_name}' 的信息: {error_msg}")
            response_content = {
                "status": "info_not_found",
                "drug_name": drug_name,
                "message": f"抱歉，未能查询到关于药物 '{drug_name}' 的详细信息 ({error_msg})。"
            }
        return self.send_message(sender_id, response_content)

    def _handle_interaction_check(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        request = content.get("interaction_check", {})
        drug_list = request.get("drugs", [])
        prescription_data = request.get("prescription")
        sender_id = message.get("sender_id", "unknown")
        
        drugs_to_check = []
        if drug_list and isinstance(drug_list, list):
            drugs_to_check = [str(d).strip() for d in drug_list if str(d).strip()]
        elif prescription_data and isinstance(prescription_data, dict):
            meds = prescription_data.get("medications", [])
            drugs_to_check = [med.get("name", "").strip() for med in meds if med.get("name", "").strip()]
            
        if len(drugs_to_check) < 2:
            return self.send_message(sender_id, {"status": "not_applicable", "message": "需要至少两种药物才能检查相互作用。"})
            
        logger.info(f"药剂师 {self.name} 正在检查药物相互作用: {', '.join(drugs_to_check)}")
        interactions = self._check_drug_interactions_with_llm(drugs_to_check)
        
        if interactions:
            formatted_interactions = []
            high_severity_found = False
            
            for inter in interactions:
                pair = inter.get("drug_pair", ["未知", "未知"])
                severity = inter.get("severity", "未知").lower()
                desc = inter.get("description", "无描述")
                rec = inter.get("recommendation", "无建议")
                formatted_interactions.append(f"- {pair[0]} 与 {pair[1]} ({severity}): {desc} [建议: {rec}]")
                if severity in ["严重", "severe", "high", "major"]:
                    high_severity_found = True
                    
            interaction_msg = "检测到以下潜在药物相互作用:\n" + "\n".join(formatted_interactions)
            if high_severity_found:
                interaction_msg += "\n\n**警告：检测到严重相互作用，请务必咨询医生或药剂师！**"
                
            response_content = {
                "status": "interactions_found",
                "drugs_checked": drugs_to_check,
                "interactions": interactions,
                "message": interaction_msg
            }
        else:
            logger.info(f"未发现药物 {', '.join(drugs_to_check)} 之间的显著相互作用。")
            response_content = {
                "status": "no_interactions_found",
                "drugs_checked": drugs_to_check,
                "message": f"根据当前分析，未在药物 {', '.join(drugs_to_check)} 之间发现显著的相互作用。"
            }
        return self.send_message(sender_id, response_content)

    def _handle_patient_prescription_query(self, message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content", {})
        query_data = content.get("patient_query_about_prescription", {})
        patient_id = query_data.get("patient_id")
        query = query_data.get("query")
        prescription = query_data.get("prescription")
        context_id = query_data.get("context_id")
        sender_id = message.get("sender_id", "unknown")
        
        if not patient_id or not query or not prescription:
            return self.send_message(sender_id, {"status": "error", "message": "处理患者处方提问失败：缺少必要信息。"})
            
        logger.info(f"药剂师 {self.name} 收到患者 {patient_id} 关于处方的提问: '{query[:50]}...'")
        
        med_list = "\n".join([f"- {m.get('name')} ({m.get('dosage')}, {m.get('frequency')})" for m in prescription.get("medications", [])])
        instructions = prescription.get("instructions", "遵医嘱")
        notes = prescription.get("notes", "无特殊说明")
        
        prompt = f"""作为一名专业的药剂师，请根据以下处方信息，回答患者的提问。请确保回答专业、准确、易懂，并且【不要提供新的医疗建议或诊断】。
当前处方:\n{med_list}\n用法说明: {instructions}\n注意事项/随访: {notes}
患者的问题: "{query}"
请针对患者的问题进行回答。如果问题超出药剂师职责范围（例如询问诊断细节），请建议患者咨询医生。回复请简洁明了。"""
        
        try:
            answer = self.llm_service.generate_response(
                prompt=prompt,
                system_message="你是一位耐心、专业的药剂师，正在解答患者关于处方用药的疑问。",
                temperature=0.3,
                max_tokens=250
            )
            
            logger.info(f"药剂师为患者 {patient_id} 生成的回答: {answer[:100]}...")
            
            if self.memory_system:
                self.memory_system.add_conversation_entry(
                    patient_id,
                    self.role,
                    answer,
                    metadata={"consultation_id": context_id, "agent_id": self.id}
                )
                
            response_content = {
                "status": "info_provided",
                "message": answer,
                "patient_id": patient_id,
                "context_id": context_id
            }
            return self.send_message(sender_id, response_content)
            
        except Exception as e:
            logger.error(f"回答患者 {patient_id} 处方问题时出错: {e}", exc_info=True)
            error_message = "抱歉，我在回答您关于处方的问题时遇到了技术问题，请稍后再试或咨询医生。"
            
            if self.memory_system:
                self.memory_system.add_conversation_entry(
                    patient_id,
                    self.role,
                    error_message,
                    metadata={"consultation_id": context_id, "agent_id": self.id, "is_error": True}
                )
                
            return self.send_message(sender_id, {"status": "error", "message": error_message})

    # --- LLM 调用方法 ---

    def _validate_prescription_with_llm(
        self,
        prescription: Dict[str, Any],
        patient_id: Optional[str] = None,
        diagnosis_info: Optional[Dict[str, Any]] = None  # 添加诊断信息参数
    ) -> Dict[str, Any]:
        """使用LLM审核处方 (改进 Prompt 和错误处理, 加入诊断信息)"""
        medications = prescription.get("medications", [])
        if not medications:
            return {"valid": False, "issues": ["处方中没有药物"], "warnings": [], "recommendations": [], "notes": "空处方"}

        medication_details = []
        for i, med in enumerate(medications):
            name = med.get('name', f'药物{i+1}')
            dose = med.get('dosage', '未指定')
            freq = med.get('frequency', '未指定')
            dur = med.get('duration', '未指定')  # 尝试获取疗程
            medication_details.append(f"- {name}: {dose}, {freq}, 疗程: {dur}")
        medication_text = "\n".join(medication_details)
        instructions = prescription.get("instructions", "无")
        notes = prescription.get("notes", "无")

        # 构建诊断信息字符串 (如果提供)
        diagnosis_context = "无可用诊断信息。"
        if diagnosis_info and isinstance(diagnosis_info, dict):
            cond = diagnosis_info.get('condition', '未指定')
            severity = diagnosis_info.get('severity', '未知')
            explanation = diagnosis_info.get('explanation', '')  # 获取解释
            diagnosis_context = f"相关诊断信息:\n诊断: {cond}\n严重程度: {severity}\n诊断说明: {explanation[:150]}..."  # 限制长度

        # --- 改进 Prompt: 加入诊断上下文, 再次强调 JSON ---
        prompt = f"""作为一位资深临床药剂师，请基于患者的部分诊断信息和以下处方，严格审核其合理性、安全性及潜在风险。

{diagnosis_context}

处方信息:
{medication_text}

医嘱/用法说明: {instructions}
其他说明/随访建议: {notes}
{f'患者ID (供参考): {patient_id}' if patient_id else ''}

请重点评估以下方面，并结合诊断信息判断（例如，药物是否符合适应症）:
1. 剂量与用法: 每个药物的剂量、频率、疗程是否清晰、常规且安全？
2. 适应症符合性: 药物组合是否与提供的诊断信息或常见用途相符？
3. 药物相互作用: 处方内的药物之间是否存在显著相互作用？
4. 禁忌症/注意事项: 是否存在明显的禁忌或重要提醒？
5. 说明清晰度: 医嘱是否清晰完整？

请【务必只返回】一个JSON对象，严格遵循以下格式，【不要包含任何】 markdown 标记 (如 ```json) 或其他解释文字:
{{{{
  "valid": true,
  "issues": [],
  "warnings": [],
  "recommendations": [],
  "notes": "处方合理，未发现明显问题。"
}}}}
如果发现问题，请修改相应字段，例如：
{{{{
  "valid": false,
  "issues": ["药物X剂量可能偏高，建议复核", "疗程未指定"],
  "warnings": ["药物X与药物Z联用可能增加出血风险"],
  "recommendations": ["请确认药物X的准确剂量", "请补充疗程"],
  "notes": "处方存在剂量和相互作用风险，需修改。"
}}}}
"""
        try:
            # --- 增加 max_tokens ---
            response = self.llm_service.generate_response(
                prompt=prompt,
                system_message="你是一位经验丰富、极其严谨的临床药剂师。请仔细检查处方，并【严格按照要求的JSON格式】输出反馈，【不要输出任何其他文字】。",
                temperature=0.1,
                max_tokens=800  # 再次增加 Token 限制
            )
            # --------------------------
            logger.debug(f"处方审核LLM响应原文: '{response}'")  # 记录原始响应

            # --- 改进 JSON 解析和验证 ---
            json_part = response.strip()
            # 尝试更鲁棒地去除可能的代码块标记和前后缀文本
            match = re.search(r'\{.*\}', json_part, re.DOTALL)  # 查找被{}包裹的最外层JSON
            if match:
                json_part = match.group(0)
            else:
                logger.warning(f"LLM响应中未找到有效的 JSON 对象结构。原始响应: {response[:200]}...")
                # 仍然尝试直接解析，可能LLM正好返回了裸JSON
                pass  # 继续尝试 json.loads

            try:
                result = json.loads(json_part)
                if not isinstance(result, dict) or "valid" not in result:
                    logger.error(f"LLM处方审核返回了无效的JSON结构 (缺少 'valid' 字段)。解析部分: '{json_part[:200]}...'")
                    raise ValueError("LLM返回的JSON结构无效")

            except json.JSONDecodeError as json_err:
                logger.error(f"解析处方审核LLM响应失败: {json_err}. 解析部分: '{json_part[:200]}...' Raw response: {response}")
                error_note = f"系统无法解析LLM的审核反馈({json_err})。原始反馈: {response[:200]}..."
                return {"valid": False, "issues": ["系统无法解析审核反馈"], "warnings": ["LLM未返回有效JSON"], "recommendations": ["请人工复核"], "notes": error_note}
            # ----------------------------

            # 验证和清理返回结果
            result["valid"] = bool(result.get("valid", False))
            result["issues"] = result.get("issues", []) if isinstance(result.get("issues"), list) else []
            result["warnings"] = result.get("warnings", []) if isinstance(result.get("warnings"), list) else []
            result["recommendations"] = result.get("recommendations", []) if isinstance(result.get("recommendations"), list) else []
            result["notes"] = result.get("notes", "") if isinstance(result.get("notes"), str) else ""
            if result["issues"]:
                result["valid"] = False  # 有 issue 则必定无效
            logger.info(f"处方审核LLM解析成功: Valid={result['valid']}, Issues={len(result['issues'])}, Warnings={len(result['warnings'])}")
            return result

        except Exception as e:
            logger.error(f"LLM处方审核过程发生错误: {str(e)}.", exc_info=True)
            return {"valid": False, "issues": ["系统审核时发生内部错误"], "warnings": [f"错误详情: {str(e)}"], "recommendations": ["请人工复核"], "notes": "系统错误导致审核未完成。"}

    def _get_drug_info_with_llm(self, drug_name: str) -> Dict[str, Any]:
        prompt = f"""请提供关于药物 "{drug_name}" 的详细信息。严格按JSON格式返回(字段: "drug_name", "description", "common_uses", "common_dosage", "common_side_effects", "serious_side_effects", "contraindications", "warnings_precautions", "storage")。找不到返回{{"drug_name":"{drug_name}", "error":"信息未找到"}}。"""
        try:
            response = self.llm_service.generate_response(
                prompt=prompt,
                system_message="你是一位专业的药学信息数据库。请根据药物名称提供准确、全面的结构化信息（JSON格式）。",
                temperature=0.1,
                max_tokens=500
            )
            logger.debug(f"药物信息查询 LLM 响应 for '{drug_name}': {response}")
            
            json_part = response.strip()
            match = re.search(r'\{.*\}', json_part, re.DOTALL)
            json_part = match.group(0) if match else json_part  # Try extracting json object
            
            drug_info = json.loads(json_part)
            if drug_info.get("drug_name", "").lower() != drug_name.lower() and "error" not in drug_info:
                logger.warning(f"LLM 返回的药物信息名称 ('{drug_info.get('drug_name')}') 与查询名称 ('{drug_name}') 不完全匹配。")
            return drug_info
        except Exception as e:
            logger.error(f"LLM获取药物 '{drug_name}' 信息过程发生错误: {str(e)}. Raw: {response if 'response' in locals() else 'N/A'}")
            return {"drug_name": drug_name, "error": f"查询时发生系统错误: {str(e)}"}

    def _check_drug_interactions_with_llm(self, drug_list: List[str]) -> List[Dict[str, Any]]:
        if len(drug_list) < 2:
            return []
            
        unique_drugs = sorted(list(set(filter(None, [d.strip() for d in drug_list]))))
        if len(unique_drugs) < 2:
            return []
            
        drug_list_str = ", ".join(f'"{drug}"' for drug in unique_drugs)
        prompt = f"""请检查以下药物之间所有可能的两两组合是否存在已知的、临床显著的相互作用: 药物列表: [{drug_list_str}]。严格按JSON列表格式返回(字段: "drug_pair", "severity", "description", "recommendation")。无相互作用返回[]。"""
        
        try:
            response = self.llm_service.generate_response(
                prompt=prompt,
                system_message="你是一个专业的药物相互作用数据库查询引擎。请仅以JSON列表格式返回已知的、临床显著的相互作用信息。",
                temperature=0.0,
                max_tokens=max(500, len(unique_drugs) * 150)
            )
            logger.debug(f"药物相互作用检查 LLM 响应 for {unique_drugs}: {response}")
            
            json_part = response.strip()
            # 查找最外层列表
            match = re.search(r'$.*$', json_part, re.DOTALL)
            json_part = match.group(0) if match else json_part
            
            if json_part == '[]':
                return []
                
            interactions = json.loads(json_part)
            if isinstance(interactions, list) and all(isinstance(item, dict) for item in interactions):
                return interactions
            else:
                logger.error(f"LLM药物相互作用检查返回了无效的格式。Raw: {response}")
                return []
        except Exception as e:
            logger.error(f"LLM药物相互作用检查过程发生错误: {str(e)}. Raw: {response if 'response' in locals() else 'N/A'}")
            return []
