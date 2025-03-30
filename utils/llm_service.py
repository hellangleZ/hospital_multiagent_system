#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LLM服务类，用于与Azure OpenAI服务交互
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Union
import asyncio
from openai import AzureOpenAI
from config.settings import Settings

logger = logging.getLogger("Hospital-MultiAgent-System")

class LLMService:
    """LLM服务类，处理与Azure OpenAI的交互"""
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        初始化LLM服务
        
        Args:
            settings: 系统配置
        """
        if settings is None:
            settings = Settings()
        
        self.settings = settings
        self.llm_config = settings.llm_config
        
        # 初始化Azure OpenAI客户端
        self.client = self._initialize_azure_client()
        
    def _initialize_azure_client(self) -> AzureOpenAI:
        """
        初始化Azure OpenAI客户端
        
        Returns:
            AzureOpenAI客户端实例
        """
        try:
            api_key = self.llm_config.get("api_key")
            api_version = self.llm_config.get("api_version")
            endpoint = self.llm_config.get("endpoint")
            
            # 确保endpoint包含http/https协议前缀
            if endpoint and not endpoint.startswith(("http://", "https://")):
                logger.warning(f"Azure OpenAI endpoint URL '{endpoint}' 缺少协议前缀，自动添加'https://'")
                endpoint = "https://" + endpoint
                self.llm_config["endpoint"] = endpoint
                
            # 记录初始化信息（注意不要记录完整的API密钥）
            logger.info(f"正在初始化Azure OpenAI客户端，API版本：{api_version}")
            logger.info(f"端点URL：{endpoint}")
            if api_key:
                masked_key = api_key[:4] + "***" + api_key[-4:] if len(api_key) > 8 else "***" 
                logger.info(f"API密钥（部分掩码）：{masked_key}")
            else:
                logger.warning("未提供API密钥")
                
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint
            )
            logger.info("Azure OpenAI客户端初始化成功")
            return client
        except Exception as e:
            logger.error(f"Azure OpenAI客户端初始化失败: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
            if hasattr(e, '__traceback__'):
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
            raise

    def generate_response(
        self, 
        prompt: str, 
        system_message: str = "你是一个医疗助手，提供准确、专业的医疗建议。",
        max_tokens: int = 800,
        temperature: float = 0.7
    ) -> str:
        """
        生成LLM响应
        
        Args:
            prompt: 用户提示
            system_message: 系统消息
            max_tokens: 最大令牌数
            temperature: 温度参数(创造性)
        
        Returns:
            LLM生成的响应文本
        """
        try:
            # 记录请求信息
            deployment_name = self.llm_config.get("deployment_name")
            logger.info(f"正在调用LLM API，模型：{deployment_name}，最大令牌：{max_tokens}，温度：{temperature}")
            logger.info(f"系统消息：{system_message[:50]}{'...' if len(system_message) > 50 else ''}")
            logger.info(f"提示词（前50个字符）：{prompt[:50]}{'...' if len(prompt) > 50 else ''}")
            
            # 记录网络状态检查
            import socket
            try:
                # 尝试解析Azure端点的主机名
                endpoint = self.llm_config.get("endpoint", "")
                if endpoint:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(endpoint)
                    hostname = parsed_url.netloc
                    ip = socket.gethostbyname(hostname)
                    logger.info(f"成功解析主机名 {hostname} 到 IP：{ip}")
                    
                    # 检查是否可以连接到端口
                    port = 443  # HTTPS默认端口
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((hostname, port))
                    if result == 0:
                        logger.info(f"成功连接到 {hostname}:{port}")
                    else:
                        logger.warning(f"无法连接到 {hostname}:{port}，错误码：{result}")
                    sock.close()
            except Exception as network_error:
                logger.warning(f"网络检查失败: {str(network_error)}")
            
            # 开始计时
            import time
            start_time = time.time()
            
            # 实际调用API
            response = self.client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # 记录响应时间和基本信息
            elapsed_time = time.time() - start_time
            logger.info(f"LLM API调用成功，耗时：{elapsed_time:.2f}秒")
            content = response.choices[0].message.content
            logger.info(f"响应内容（前50个字符）：{content[:50]}{'...' if len(content) > 50 else ''}")
            
            return content
        except Exception as e:
            elapsed_time = time.time() - start_time if 'start_time' in locals() else -1
            logger.error(f"LLM响应生成失败: {str(e)}，耗时：{elapsed_time:.2f}秒")
            logger.error(f"错误类型: {type(e).__name__}")
            
            # 记录更详细的错误信息
            if hasattr(e, 'response'):
                try:
                    logger.error(f"API错误响应: {e.response.text if hasattr(e.response, 'text') else e.response}")
                    logger.error(f"API错误状态码: {e.response.status_code if hasattr(e.response, 'status_code') else 'Unknown'}")
                except:
                    pass
                    
            if hasattr(e, '__traceback__'):
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                
            # 网络错误特别处理
            if "Connection" in str(e) or "Timeout" in str(e) or "timeout" in str(e).lower():
                logger.error("检测到网络连接问题，请检查您的网络连接和防火墙设置")
                if "proxy" in str(e).lower():
                    logger.error("可能与代理设置有关，请检查您的代理配置")
            
            return f"很抱歉，我无法处理您的请求: {str(e)}"
    
    async def generate_response_async(
        self, 
        prompt: str, 
        system_message: str = "你是一个医疗助手，提供准确、专业的医疗建议。",
        max_tokens: int = 800,
        temperature: float = 0.7
    ) -> str:
        """
        异步生成LLM响应
        
        Args:
            prompt: 用户提示
            system_message: 系统消息
            max_tokens: 最大令牌数
            temperature: 温度参数(创造性)
        
        Returns:
            LLM生成的响应文本
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self.generate_response(
                prompt=prompt,
                system_message=system_message,
                max_tokens=max_tokens,
                temperature=temperature
            )
        )
    
    def analyze_symptoms(self, symptoms: List[str], medical_history: List[str] = None) -> Dict[str, Any]:
        """
        分析症状并给出初步诊断建议
        
        Args:
            symptoms: 症状列表
            medical_history: 病史列表
        
        Returns:
            诊断分析结果
        """
        if medical_history is None:
            medical_history = []
            
        prompt = f"""请分析以下症状并给出初步诊断建议:

症状: {', '.join(symptoms)}

病史: {', '.join(medical_history) if medical_history else '无'}

请以JSON格式回答，包含以下字段:
1. 可能的疾病(possible_conditions): 列出2-3种可能的疾病
2. 建议科室(recommended_department): 建议就诊的科室
3. 严重程度(severity): 1-5，5最严重
4. 建议(recommendations): 简短建议

只返回JSON格式的结果，不要有其他文字。
"""
        try:
            response = self.generate_response(prompt=prompt)
            # 解析JSON响应
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"无法解析LLM返回的JSON: {response}")
            return {
                "possible_conditions": ["无法确定"],
                "recommended_department": "内科",
                "severity": 3,
                "recommendations": ["建议进一步检查"]
            }
        except Exception as e:
            logger.error(f"症状分析失败: {str(e)}")
            return {
                "possible_conditions": ["分析失败"],
                "recommended_department": "内科",
                "severity": 3,
                "recommendations": ["系统错误，请重试"]
            }
            
    def generate_prescription_explanation(self, prescription: Dict[str, Any]) -> str:
        """
        生成处方解释
        
        Args:
            prescription: 处方信息
        
        Returns:
            处方解释文本
        """
        medications = prescription.get("medications", [])
        medications_text = "\n".join([
            f"- {med.get('name')}: {med.get('dosage')}, {med.get('frequency')}" 
            for med in medications
        ])
        
        prompt = f"""请为以下处方生成患者友好的解释:

处方药物:
{medications_text}

使用说明: {prescription.get('instructions', '无特殊说明')}

随访: {prescription.get('follow_up', '如症状加重请及时就医')}

请用简单易懂的语言解释这些药物的作用、正确用法和可能的副作用。
"""
        return self.generate_response(
            prompt=prompt, 
            system_message="你是一位经验丰富的药剂师，擅长向患者解释药物信息。",
            max_tokens=600,
            temperature=0.5
        )
    
    def check_drug_interactions(self, medications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        检查药物相互作用
        
        Args:
            medications: 药物列表
            
        Returns:
            药物相互作用列表
        """
        if not medications or len(medications) < 2:
            return []
            
        drug_names = [med.get("name", "") for med in medications if "name" in med]
        
        prompt = f"""请检查以下药物之间可能存在的相互作用:

药物列表: {', '.join(drug_names)}

请以JSON格式返回可能的药物相互作用，每个相互作用包含以下字段:
1. 相互作用药物对(drug_pair): [药物A, 药物B]
2. 严重程度(severity): "轻度", "中度", 或 "严重"
3. 描述(description): 相互作用的简短描述
4. 建议(recommendation): 如何处理这种相互作用

只返回JSON格式的结果，不要有其他文字。如果没有相互作用，返回空数组 []。
"""
        try:
            response = self.generate_response(
                prompt=prompt,
                system_message="你是一位专业药剂师，熟悉各类药物相互作用。",
                max_tokens=1000,
                temperature=0.3
            )
            # 解析JSON响应
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"无法解析LLM返回的药物相互作用JSON: {response}")
            return []
        except Exception as e:
            logger.error(f"药物相互作用检查失败: {str(e)}")
            return []