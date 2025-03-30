#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
医院多智能体系统主程序
"""

import os
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

from agents.receptionist import ReceptionistAgent
from agents.doctor import DoctorAgent
from agents.pharmacist import PharmacistAgent
from agents.scheduler import SchedulerAgent
from utils.orchestrator import Orchestrator
from utils.memory_system import MemorySystem
from utils.llm_service import LLMService
from config.settings import SETTINGS

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("hospital_system.log")
    ]
)

logger = logging.getLogger("Hospital-MultiAgent-System")

def main():
    """程序入口函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="医院多智能体系统")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--no-memory", action="store_true", help="禁用记忆持久化")
    parser.add_argument("--memory-path", type=str, default="data/memories.json", help="记忆持久化文件路径")
    args = parser.parse_args()

    # 设置日志级别
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("调试模式已启用")

    # 初始化LLM服务
    try:
        llm_service = LLMService(settings=SETTINGS)
        logger.info(f"已初始化LLM服务，模型: {SETTINGS.llm_config.get('deployment_name', '默认')}")
    except Exception as e:
        logger.error(f"初始化LLM服务失败: {str(e)}")
        llm_service = None
    
    # 初始化记忆系统 (支持短期和长期记忆)
    memory_path = None if args.no_memory else args.memory_path
    
    # 确保记忆文件目录存在
    if memory_path:
        os.makedirs(os.path.dirname(memory_path), exist_ok=True)
    
    memory_system = MemorySystem(
        persistence_path=memory_path,
        llm_service=llm_service  # 传递LLM服务以支持记忆归纳
    )
    
    logger.info(f"记忆系统已初始化，{'不' if args.no_memory else ''}使用持久化存储")
    
    # 初始化智能体
    receptionist = ReceptionistAgent(
        name="李接待",
        memory_system=memory_system,
        llm_service=llm_service
    )
    
    doctor = DoctorAgent(
        name="王医生",
        specialty="内科",
        memory_system=memory_system,
        llm_service=llm_service
    )
    
    pharmacist = PharmacistAgent(
        name="张药师",
        role="pharmacist",
        memory_system=memory_system,
        llm_service=llm_service
    )
    
    scheduler = SchedulerAgent(
        name="调度器",
        memory_system=memory_system
    )
    
    logger.info("所有智能体已初始化")
    
    # 初始化编排器
    orchestrator = Orchestrator(
        receptionist=receptionist,
        doctor=doctor,
        pharmacist=pharmacist,
        scheduler=scheduler,
        memory_system=memory_system
    )
    
    logger.info("编排器已初始化")
    
    # 注册记忆系统配置
    if memory_system and llm_service:
        # 设置短期记忆为7天
        memory_system.memory_config["short_term_days"] = 7
        # 每24小时检查一次需要归纳的记忆
        memory_system.memory_config["consolidation_interval_hours"] = 24
        logger.info("记忆系统配置已更新：短期记忆期限为7天，每24小时整合一次记忆")
    
    # 简单的交互式界面
    print("="*50)
    print("医院多智能体系统已启动")
    print("输入 'exit' 退出系统")
    print("="*50)
    
    while True:
        try:
            print("\n请输入患者信息和症状(格式: 姓名,年龄,症状1;症状2;...)")
            user_input = input("> ")
            
            if user_input.lower() == 'exit':
                break
            
            # 解析输入
            try:
                parts = user_input.split(',')
                if len(parts) < 3:
                    print("输入格式错误，请按格式输入：姓名,年龄,症状1;症状2;...")
                    continue
                
                patient_name = parts[0].strip()
                patient_age = int(parts[1].strip())
                symptoms = [s.strip() for s in parts[2].strip().split(';')]
                
                # 可选的病史
                medical_history = []
                if len(parts) > 3:
                    medical_history = [s.strip() for s in parts[3].strip().split(';')]
                
                # 处理问诊
                print(f"\n开始处理 {patient_name} 的问诊请求...")
                result = orchestrator.process_consultation(
                    patient_name=patient_name,
                    patient_age=patient_age,
                    symptoms=symptoms,
                    medical_history=medical_history
                )
                
                # 打印结果
                print("\n===== 问诊结果 =====")
                print(f"患者: {patient_name}, {patient_age}岁")
                print(f"症状: {', '.join(symptoms)}")
                if medical_history:
                    print(f"病史: {', '.join(medical_history)}")
                
                if "diagnosis" in result:
                    print(f"\n诊断结果: {result['diagnosis']}")
                
                if "recommendations" in result:
                    print("\n医生建议:")
                    for rec in result["recommendations"]:
                        print(f" - {rec}")
                
                if "prescription" in result:
                    print("\n处方药:")
                    for med in result["prescription"]:
                        dosage = med.get("dosage", "")
                        freq = med.get("frequency", "")
                        print(f" - {med.get('name', '')}: {dosage} {freq}")
                
                if "follow_up" in result:
                    print(f"\n后续跟进: {result['follow_up']}")
                    
                # 查询患者历史记忆
                patient_id = result.get("additional_info", {}).get("patient_id")
                if patient_id and memory_system:
                    print("\n===== 患者记忆信息 =====")
                    
                    # 获取记忆类别统计
                    memory_stats = memory_system.get_all_memory_categories(patient_id)
                    
                    # 短期记忆
                    print("短期记忆:")
                    for memory_type, count in memory_stats.get("short_term", {}).items():
                        print(f" - {memory_type}: {count}条记录")
                    
                    # 长期记忆
                    print("长期记忆:")
                    for memory_type, count in memory_stats.get("long_term", {}).items():
                        print(f" - {memory_type}: {count}条记录")
                    
                    # 获取长期归纳记忆
                    consolidated_memories = memory_system.get_consolidated_long_term_memories(patient_id, limit=1)
                    if consolidated_memories:
                        latest_memory = consolidated_memories[0].get("data", {})
                        print("\n最新长期归纳记忆:")
                        if "medical_issues" in latest_memory:
                            print(f"主要医疗问题: {', '.join(latest_memory.get('medical_issues', []))}")
                        if "diagnoses" in latest_memory:
                            print(f"诊断摘要: {latest_memory.get('diagnoses', '')}")
                        if "special_notes" in latest_memory:
                            print(f"特殊注意事项: {latest_memory.get('special_notes', '')}")
                    
                print("="*50)
                
            except ValueError as e:
                print(f"输入解析错误: {str(e)}")
            except Exception as e:
                print(f"处理问诊时出错: {str(e)}")
                logger.error(f"处理问诊时出错: {str(e)}", exc_info=True)
                
        except KeyboardInterrupt:
            print("\n正在退出系统...")
            break
        except Exception as e:
            print(f"发生错误: {str(e)}")
            logger.error(f"主循环中发生错误: {str(e)}", exc_info=True)
    
    print("系统已退出")

if __name__ == "__main__":
    main()