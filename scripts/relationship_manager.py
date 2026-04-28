"""
关系数据管理器
管理虚拟陪伴者的关系数据读写、更新、多陪伴者支持
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid


class RelationshipManager:
    """关系数据管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.relationship_file = self.data_dir / "relationship.json"
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        """加载关系数据"""
        if not self.relationship_file.exists():
            return self._default_data()
        try:
            with open(self.relationship_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return self._default_data()

    def _save(self, data: dict) -> None:
        """保存关系数据"""
        data["updatedAt"] = datetime.now().isoformat()
        with open(self.relationship_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _default_data(self) -> dict:
        """默认数据结构"""
        return {
            "version": "2.0",
            "initialized": False,
            "activeCompanionId": None,
            "companions": {},
            "milestones": [],
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
            "config": {
                "language": "zh-CN",
                "setupComplete": False,
                "interactionRituals": {
                    "morningCheckin": False,
                    "nightCheckin": False,
                    "anniversaryAlerts": True
                },
                "reminderEnabled": False,
                "reminderSchedule": None
            }
        }

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        data = self._load()
        return data.get("initialized", False) and data.get("activeCompanionId") is not None

    def get_active_companion(self) -> Optional[dict]:
        """获取当前活跃陪伴者"""
        data = self._load()
        active_id = data.get("activeCompanionId")
        if active_id and active_id in data.get("companions", {}):
            return data["companions"][active_id]
        return None

    def list_companions(self) -> list:
        """列出所有陪伴者"""
        data = self._load()
        companions = data.get("companions", {})
        return [
            {
                "id": cid,
                "name": c.get("agent", {}).get("name", "未命名"),
                "role": c.get("agent", {}).get("role", "未知"),
                "userName": c.get("user", {}).get("name", "未知")
            }
            for cid, c in companions.items()
        ]

    def create_companion(
        self,
        agent_name: str,
        agent_role: str,
        user_name: str,
        agent_personality: str = "",
        agent_appearance: str = "",
        agent_background: str = "",
        user_personality: str = "",
        user_background: str = "",
        how_they_met: str = "",
        special_bond: str = "",
        key_dates: list = None,
        interaction_prefs: dict = None
    ) -> str:
        """创建新陪伴者，返回陪伴者ID"""
        data = self._load()

        companion_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        companion = {
            "agent": {
                "name": agent_name,
                "role": agent_role,
                "customRole": "",
                "personality": agent_personality,
                "appearance": agent_appearance,
                "background": agent_background
            },
            "user": {
                "name": user_name,
                "personality": user_personality,
                "background": user_background
            },
            "relationship": {
                "type": agent_role,
                "howTheyMet": how_they_met,
                "sharedMemories": [],
                "specialBond": special_bond
            },
            "emotionalState": {
                "current": "neutral",
                "intensity": 0.5,
                "reasons": [],
                "lastInteraction": now,
                "interactionCount": 0,
                "consecutiveDays": 1,
                "missedDays": 0
            },
            "keyDates": key_dates or [],
            "interactionPrefs": interaction_prefs or {
                "morningCheckin": False,
                "nightCheckin": False,
                "userNickname": user_name,
                "companionNickname": agent_name
            },
            "milestones": [],
            "chatHistory": [],
            "createdAt": now,
            "updatedAt": now
        }

        data["companions"][companion_id] = companion
        data["activeCompanionId"] = companion_id
        data["initialized"] = True
        data["updatedAt"] = now

        self._save(data)
        return companion_id

    def switch_companion(self, companion_id: str) -> bool:
        """切换到指定陪伴者"""
        data = self._load()
        if companion_id in data.get("companions", {}):
            data["activeCompanionId"] = companion_id
            self._save(data)
            return True
        return False

    def update_companion(self, companion_id: str, updates: dict) -> bool:
        """更新陪伴者信息"""
        data = self._load()
        if companion_id not in data.get("companions", {}):
            return False

        companion = data["companions"][companion_id]

        # 支持嵌套更新
        for key, value in updates.items():
            if "." in key:
                parts = key.split(".")
                d = companion
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = value
            else:
                companion[key] = value

        companion["updatedAt"] = datetime.now().isoformat()
        data["updatedAt"] = datetime.now().isoformat()
        self._save(data)
        return True

    def add_memory(
        self,
        companion_id: str,
        content: str,
        importance: str = "medium",
        tags: list = None
    ) -> Optional[str]:
        """添加共同回忆"""
        data = self._load()
        if companion_id not in data.get("companions", {}):
            return None

        companion = data["companions"][companion_id]
        memories = companion["relationship"].setdefault("sharedMemories", [])

        memory_id = f"mem_{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime("%Y-%m-%d")

        memory = {
            "id": memory_id,
            "content": content,
            "date": now,
            "importance": importance,
            "mentionedCount": 0,
            "lastMentioned": now,
            "tags": tags or []
        }

        memories.append(memory)
        data["updatedAt"] = datetime.now().isoformat()
        self._save(data)
        return memory_id

    def update_memory_importance(self, companion_id: str, memory_id: str, importance: str) -> bool:
        """更新回忆重要性"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return False

        for mem in companion["relationship"].get("sharedMemories", []):
            if mem["id"] == memory_id:
                mem["importance"] = importance
                self._save(data)
                return True
        return False

    def increment_memory_mention(self, companion_id: str, memory_id: str) -> bool:
        """增加回忆被提及次数"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return False

        for mem in companion["relationship"].get("sharedMemories", []):
            if mem["id"] == memory_id:
                mem["mentionedCount"] += 1
                mem["lastMentioned"] = datetime.now().strftime("%Y-%m-%d")
                self._save(data)
                return True
        return False

    def add_milestone(self, companion_id: str, milestone_type: str, description: str, days: int) -> None:
        """添加里程碑记录"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return

        milestones = companion.setdefault("milestones", [])
        milestone_id = f"ms_{uuid.uuid4().hex[:8]}"

        milestones.append({
            "id": milestone_id,
            "type": milestone_type,
            "description": description,
            "days": days,
            "achievedAt": datetime.now().isoformat()
        })

        self._save(data)

    def delete_companion(self, companion_id: str) -> bool:
        """删除陪伴者"""
        data = self._load()
        if companion_id not in data.get("companions", {}):
            return False

        del data["companions"][companion_id]

        # 如果删除的是当前活跃的，切换到另一个
        if data.get("activeCompanionId") == companion_id:
            remaining = list(data["companions"].keys())
            data["activeCompanionId"] = remaining[0] if remaining else None

        data["initialized"] = len(remaining) > 0 if remaining else False
        data["updatedAt"] = datetime.now().isoformat()
        self._save(data)
        return True

    def export_data(self) -> dict:
        """导出所有数据（备份用）"""
        return self._load()

    def import_data(self, import_data: dict) -> bool:
        """导入数据"""
        try:
            # 验证基本结构
            if "version" not in import_data or "companions" not in import_data:
                return False

            self._save(import_data)
            return True
        except Exception:
            return False

    def get_profile_summary(self, companion_id: str = None) -> dict:
        """获取陪伴者档案摘要"""
        data = self._load()
        target_id = companion_id or data.get("activeCompanionId")

        if not target_id:
            return {}

        companion = data.get("companions", {}).get(target_id, {})
        if not companion:
            return {}

        # 计算相识天数
        created = datetime.fromisoformat(companion.get("createdAt", datetime.now().isoformat()))
        days_together = (datetime.now() - created).days

        return {
            "id": target_id,
            "agentName": companion.get("agent", {}).get("name", ""),
            "agentRole": companion.get("agent", {}).get("role", ""),
            "agentPersonality": companion.get("agent", {}).get("personality", ""),
            "userName": companion.get("user", {}).get("name", ""),
            "daysTogether": days_together,
            "memoryCount": len(companion.get("relationship", {}).get("sharedMemories", [])),
            "emotionalState": companion.get("emotionalState", {}).get("current", "neutral"),
            "milestoneCount": len(companion.get("milestones", []))
        }


if __name__ == "__main__":
    # 测试
    manager = RelationshipManager(r"C:\Users\zero\.qclaw\skills\virtual-companion\references")
    print("数据加载成功")
    print(f"已初始化: {manager.is_initialized()}")
    companions = manager.list_companions()
    print(f"陪伴者列表: {companions}")
