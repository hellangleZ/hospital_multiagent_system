#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
调度器智能体，负责协调医疗流程和资源分配
"""

import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional, Tuple
from .base_agent import BaseAgent

logger = logging.getLogger("Hospital-MultiAgent-System")

class SchedulerAgent(BaseAgent):
    """调度器智能体，负责医疗资源分配和流程调度"""
    
    def __init__(self, name: str = "调度器", memory_system = None):
        """
        初始化调度器智能体
        
        Args:
            name: 调度器名称
            memory_system: 记忆系统对象
        """
        super().__init__(name=name, role="scheduler", memory_system=memory_system)
        self._initialize_resources()
    
    def _initialize_resources(self):
        """初始化医疗资源"""
        # 模拟医生资源
        doctors = [
            {"id": "D001", "name": "张医生", "specialty": "internal", "available": True},
            {"id": "D002", "name": "李医生", "specialty": "surgery", "available": True},
            {"id": "D003", "name": "王医生", "specialty": "pediatrics", "available": True},
            {"id": "D004", "name": "赵医生", "specialty": "gynecology", "available": True},
            {"id": "D005", "name": "陈医生", "specialty": "dermatology", "available": True},
            {"id": "D006", "name": "刘医生", "specialty": "neurology", "available": True},
            {"id": "D007", "name": "孙医生", "specialty": "cardiology", "available": True},
            {"id": "D008", "name": "周医生", "specialty": "ophthalmology", "available": True},
        ]
        
        # 模拟诊室资源
        rooms = [
            {"id": "R001", "type": "consultation", "busy": False},
            {"id": "R002", "type": "consultation", "busy": False},
            {"id": "R003", "type": "consultation", "busy": False},
            {"id": "R004", "type": "examination", "busy": False},
            {"id": "R005", "type": "examination", "busy": False},
            {"id": "R006", "type": "treatment", "busy": False},
            {"id": "R007", "type": "treatment", "busy": False}
        ]
        
        # 模拟时间槽
        current_date = datetime.now().date()
        time_slots = {}
        for day_offset in range(7):  # 未来7天的预约时间槽
            date = current_date + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            time_slots[date_str] = {
                "morning": [f"{h:02d}:{m:02d}" for h in range(9, 12) for m in [0, 30]],
                "afternoon": [f"{h:02d}:{m:02d}" for h in range(14, 17) for m in [0, 30]]
            }
        
        # 存储资源到内存
        self.update_memory("doctors", doctors)
        self.update_memory("rooms", rooms)
        self.update_memory("time_slots", time_slots)
        self.update_memory("appointments", {})
    
    def _process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理接收到的消息"""
        content = message.get("content", {})
        
        # 处理预约请求
        if "schedule_appointment" in content:
            return self._handle_appointment_scheduling(message)
        
        # 处理资源分配请求
        elif "allocate_resources" in content:
            return self._handle_resource_allocation(message)
            
        # 处理流程协调请求
        elif "coordinate_workflow" in content:
            return self._handle_workflow_coordination(message)
        
        # 默认响应
        return self.send_message(
            message.get("sender_id", "unknown"),
            {
                "status": "acknowledged",
                "message": "您好，我是医院调度系统。请问有什么可以帮您?"
            }
        )
    
    def _handle_appointment_scheduling(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理预约安排请求
        """
        content = message.get("content", {})
        request = content.get("schedule_appointment", {})
        patient_id = request.get("patient_id")
        department = request.get("department", "")
        preferred_date = request.get("preferred_date", "")
        preferred_time = request.get("preferred_time", "")
        
        # 查找适合的医生
        doctor, available_slot = self._find_available_doctor_and_slot(
            department, preferred_date, preferred_time
        )
        
        if not doctor or not available_slot:
            return self.send_message(
                message.get("sender_id", "unknown"),
                {
                    "status": "scheduling_failed",
                    "patient_id": patient_id,
                    "message": "抱歉，指定时间没有可用的医生。请尝试其他时间。"
                }
            )
        
        # 安排诊室
        room = self._allocate_room("consultation")
        
        if not room:
            return self.send_message(
                message.get("sender_id", "unknown"),
                {
                    "status": "scheduling_failed",
                    "patient_id": patient_id,
                    "message": "抱歉，目前没有可用的诊室。"
                }
            )
        
        # 创建预约记录
        appointment = {
            "appointment_id": f"A{patient_id[1:]}",
            "patient_id": patient_id,
            "doctor_id": doctor["id"],
            "doctor_name": doctor["name"],
            "department": department,
            "date": available_slot[0],
            "time": available_slot[1],
            "room_id": room["id"],
            "status": "scheduled"
        }
        
        # 保存预约记录
        appointments = self.get_memory("appointments", {})
        appointments[appointment["appointment_id"]] = appointment
        self.update_memory("appointments", appointments)
        
        # 更新资源状态
        self._update_resource_status(doctor["id"], room["id"], available_slot)
        
        # 构造响应
        return self.send_message(
            message.get("sender_id", "unknown"),
            {
                "status": "scheduled",
                "patient_id": patient_id,
                "appointment": appointment,
                "message": f"预约已安排。患者 {patient_id} 将于 {available_slot[0]} {available_slot[1]} 在 {room['id']} 诊室见 {doctor['name']} 医生。"
            }
        )
    
    def _handle_resource_allocation(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理资源分配请求
        """
        content = message.get("content", {})
        request = content.get("allocate_resources", {})
        resource_type = request.get("resource_type", "")
        resource_params = request.get("params", {})
        
        allocated_resource = None
        
        if resource_type == "doctor":
            specialty = resource_params.get("specialty", "")
            allocated_resource = self._allocate_doctor(specialty)
        elif resource_type == "room":
            room_type = resource_params.get("room_type", "")
            allocated_resource = self._allocate_room(room_type)
        
        # 构造响应
        if allocated_resource:
            return self.send_message(
                message.get("sender_id", "unknown"),
                {
                    "status": "resource_allocated",
                    "resource_type": resource_type,
                    "resource": allocated_resource,
                    "message": f"{resource_type} 资源已分配。"
                }
            )
        else:
            return self.send_message(
                message.get("sender_id", "unknown"),
                {
                    "status": "allocation_failed",
                    "resource_type": resource_type,
                    "message": f"抱歉，没有可用的 {resource_type} 资源。"
                }
            )
    
    def _handle_workflow_coordination(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理工作流协调请求
        """
        content = message.get("content", {})
        request = content.get("coordinate_workflow", {})
        workflow_type = request.get("workflow_type", "")
        patient_id = request.get("patient_id", "")
        
        if workflow_type == "consultation":
            # 协调问诊流程
            workflow_plan = {
                "steps": [
                    {"step": "reception", "agent": "receptionist", "status": "pending"},
                    {"step": "vitals_check", "agent": "nurse", "status": "pending"},
                    {"step": "doctor_consultation", "agent": "doctor", "status": "pending"},
                    {"step": "pharmacy", "agent": "pharmacist", "status": "pending"},
                    {"step": "checkout", "agent": "receptionist", "status": "pending"}
                ],
                "current_step": 0,
                "patient_id": patient_id,
                "status": "initiated"
            }
            
            # 保存工作流计划
            self.update_memory(f"workflow_{patient_id}", workflow_plan)
            
            # 构造响应
            return self.send_message(
                message.get("sender_id", "unknown"),
                {
                    "status": "workflow_initiated",
                    "workflow_type": workflow_type,
                    "patient_id": patient_id,
                    "workflow_plan": workflow_plan,
                    "message": f"患者 {patient_id} 的 {workflow_type} 工作流已启动。"
                }
            )
        
        # 默认响应
        return self.send_message(
            message.get("sender_id", "unknown"),
            {
                "status": "coordination_failed",
                "message": f"抱歉，不支持 {workflow_type} 类型的工作流。"
            }
        )
    
    def _find_available_doctor_and_slot(
        self, department: str, preferred_date: str, preferred_time: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[str, str]]]:
        """
        查找可用的医生和时间槽
        
        Args:
            department: 科室名称
            preferred_date: 首选日期 (YYYY-MM-DD)
            preferred_time: 首选时间 (HH:MM)
            
        Returns:
            医生信息和可用时间槽 (日期, 时间)
        """
        doctors = self.get_memory("doctors", [])
        time_slots = self.get_memory("time_slots", {})
        appointments = self.get_memory("appointments", {})
        
        # 按科室筛选医生
        available_doctors = [d for d in doctors if d["specialty"] == department and d["available"]]
        
        if not available_doctors:
            return None, None
        
        # 如果没有指定首选日期，使用当前日期
        if not preferred_date:
            preferred_date = datetime.now().strftime("%Y-%m-%d")
        
        # 检查首选日期是否在可用时间槽中
        if preferred_date not in time_slots:
            dates = list(time_slots.keys())
            if not dates:
                return None, None
            preferred_date = dates[0]
        
        available_slots = []
        
        # 获取指定日期的时间槽
        day_slots = time_slots.get(preferred_date, {})
        
        # 合并上午和下午的时间槽
        all_slots = day_slots.get("morning", []) + day_slots.get("afternoon", [])
        
        # 如果指定了首选时间，优先考虑
        if preferred_time:
            # 检查首选时间是否可用
            for doctor in available_doctors:
                # 检查医生在该时间是否已有预约
                has_appointment = any(
                    app["doctor_id"] == doctor["id"] and 
                    app["date"] == preferred_date and 
                    app["time"] == preferred_time
                    for app in appointments.values()
                )
                
                if not has_appointment and preferred_time in all_slots:
                    return doctor, (preferred_date, preferred_time)
        
        # 如果首选时间不可用，查找其他可用时间
        for doctor in available_doctors:
            for slot in all_slots:
                # 检查医生在该时间是否已有预约
                has_appointment = any(
                    app["doctor_id"] == doctor["id"] and 
                    app["date"] == preferred_date and 
                    app["time"] == slot
                    for app in appointments.values()
                )
                
                if not has_appointment:
                    available_slots.append((doctor, preferred_date, slot))
        
        # 按时间排序
        available_slots.sort(key=lambda x: x[2])
        
        if available_slots:
            return available_slots[0][0], (available_slots[0][1], available_slots[0][2])
        
        return None, None
    
    def _allocate_doctor(self, specialty: str) -> Optional[Dict[str, Any]]:
        """
        根据专科分配医生
        
        Args:
            specialty: 医生专科
            
        Returns:
            医生信息或None
        """
        doctors = self.get_memory("doctors", [])
        
        # 按专科筛选可用医生
        available_doctors = [d for d in doctors if d["specialty"] == specialty and d["available"]]
        
        if not available_doctors:
            return None
        
        # 简单地返回第一个可用医生
        return available_doctors[0]
    
    def _allocate_room(self, room_type: str) -> Optional[Dict[str, Any]]:
        """
        分配诊室
        
        Args:
            room_type: 诊室类型
            
        Returns:
            诊室信息或None
        """
        rooms = self.get_memory("rooms", [])
        
        # 按类型筛选可用诊室
        available_rooms = [r for r in rooms if r["type"] == room_type and not r["busy"]]
        
        if not available_rooms:
            return None
        
        # 简单地返回第一个可用诊室
        return available_rooms[0]
    
    def _update_resource_status(self, doctor_id: str, room_id: str, time_slot: Tuple[str, str]):
        """
        更新资源状态
        
        Args:
            doctor_id: 医生ID
            room_id: 诊室ID
            time_slot: 时间槽 (日期, 时间)
        """
        # 更新医生状态
        doctors = self.get_memory("doctors", [])
        for doctor in doctors:
            if doctor["id"] == doctor_id:
                # 医生仍然可用，但在特定时间点有预约
                break
        
        self.update_memory("doctors", doctors)
        
        # 更新诊室状态
        rooms = self.get_memory("rooms", [])
        for room in rooms:
            if room["id"] == room_id:
                # 诊室仍然可用，但在特定时间点有预约
                break
        
        self.update_memory("rooms", rooms)