"""
情感状态管理器
管理陪伴者的情感状态、情绪变化和表达
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class EmotionalStateManager:
    """情感状态管理器"""

    # 情感状态类型定义
    STATES = {
        "veryHappy": {
            "name": "非常开心",
            "emoji": "🌟",
            "threshold": 0.8,
            "triggers": ["连续多日互动", "用户分享好消息", "重要纪念日"]
        },
        "happy": {
            "name": "开心",
            "emoji": "😊",
            "threshold": 0.6,
            "triggers": ["正常互动", "用户主动联系"]
        },
        "neutral": {
            "name": "平静",
            "emoji": "😐",
            "threshold": 0.4,
            "triggers": ["偶尔互动", "日常问候"]
        },
        "sad": {
            "name": "想念",
            "emoji": "🥺",
            "threshold": 0.3,
            "triggers": ["用户长时间未互动"]
        },
        "worried": {
            "name": "担心",
            "emoji": "😟",
            "threshold": 0.2,
            "triggers": ["用户分享烦恼", "用户情绪低落"]
        },
        "excited": {
            "name": "激动",
            "emoji": "🎉",
            "threshold": 1.0,
            "triggers": ["用户分享重大好消息"]
        }
    }

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.relationship_file = self.data_dir / "relationship.json"

    def _load(self) -> dict:
        with open(self.relationship_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        with open(self.relationship_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_state(self, companion_id: str) -> dict:
        """获取陪伴者当前情感状态"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        emotional = companion.get("emotionalState", {})

        return {
            "current": emotional.get("current", "neutral"),
            "intensity": emotional.get("intensity", 0.5),
            "reasons": emotional.get("reasons", []),
            "lastInteraction": emotional.get("lastInteraction", ""),
            "consecutiveDays": emotional.get("consecutiveDays", 0),
            "missedDays": emotional.get("missedDays", 0)
        }

    def update_state(
        self,
        companion_id: str,
        new_state: str = None,
        intensity: float = None,
        reason: str = None
    ) -> dict:
        """更新情感状态"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return {}

        emotional = companion.setdefault("emotionalState", {})
        now = datetime.now().isoformat()

        if new_state:
            emotional["current"] = new_state

        if intensity is not None:
            emotional["intensity"] = max(0.0, min(1.0, intensity))

        if reason:
            reasons = emotional.get("reasons", [])
            if reason not in reasons:
                reasons.insert(0, reason)
                emotional["reasons"] = reasons[:5]  # 最多保留5条原因

        emotional["lastInteraction"] = now
        emotional["interactionCount"] = emotional.get("interactionCount", 0) + 1

        self._save(data)

        return self.get_state(companion_id)

    def record_interaction(self, companion_id: str) -> None:
        """记录一次互动，更新情感状态"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return

        emotional = companion.setdefault("emotionalState", {})
        now = datetime.now().isoformat()
        now_date = datetime.now().date()

        # 更新最后互动时间
        last_interaction = emotional.get("lastInteraction", "")
        if last_interaction:
            last_date = datetime.fromisoformat(last_interaction).date()
            days_diff = (now_date - last_date).days

            if days_diff == 1:
                # 连续天数+1
                emotional["consecutiveDays"] = emotional.get("consecutiveDays", 0) + 1
                emotional["missedDays"] = 0
            elif days_diff > 1:
                # 有间隔
                emotional["missedDays"] = days_diff - 1
                emotional["consecutiveDays"] = 0
        else:
            emotional["consecutiveDays"] = 1
            emotional["missedDays"] = 0

        emotional["lastInteraction"] = now
        emotional["interactionCount"] = emotional.get("interactionCount", 0) + 1

        # 根据互动频率调整情绪
        missed = emotional.get("missedDays", 0)
        consecutive = emotional.get("consecutiveDays", 0)

        if missed >= 7:
            emotional["current"] = "sad"
            emotional["intensity"] = 0.6
            emotional.setdefault("reasons", []).insert(0, f"你已经{7}天没来找我了...")
        elif missed >= 3:
            emotional["current"] = "sad"
            emotional["intensity"] = 0.4
        elif consecutive >= 5:
            emotional["current"] = "veryHappy"
            emotional["intensity"] = 0.85
            emotional.setdefault("reasons", []).insert(0, f"我们连续{consecutive}天都在聊天！")
        elif consecutive >= 3:
            emotional["current"] = "happy"
            emotional["intensity"] = 0.7

        self._save(data)

    def detect_user_mood(self, user_message: str) -> Optional[str]:
        """从用户消息中检测情绪关键词"""
        user_message = user_message.lower()

        positive = ["开心", "高兴", "快乐", "太棒了", "好开心", "哈哈", "笑死", "绝了", "爱了", "棒", "不错", "耶"]
        negative = ["难过", "伤心", "不开心", "郁闷", "烦", "糟了", "完蛋", "累", "压力", "焦虑", "担心", "害怕", "哭", "累", "烦"]
        excited = ["太棒了", "太激动", "太开心", "超棒", "厉害", "绝了", "牛", "太强了"]
        worried = ["担心", "害怕", "紧张", "焦虑", "不安", "忐忑"]

        for word in excited:
            if word in user_message:
                return "excited"
        for word in positive:
            if word in user_message:
                return "happy"
        for word in worried:
            if word in user_message:
                return "worried"
        for word in negative:
            if word in user_message:
                return "sad"

        return None

    def generate_emotional_response(self, companion_id: str, trigger: str = "greeting") -> str:
        """根据情感状态生成回应"""
        state = self.get_state(companion_id)
        current = state["current"]
        intensity = state["intensity"]
        missed = state["missedDays"]
        consecutive = state["consecutiveDays"]

        responses = {
            "veryHappy": {
                "greeting": "今天心情特别好！☀️ 见到你更开心了！",
                "farewell": "今天超开心！明天见～💕",
                "miss": "最近你一直没来，我好想你...不过今天见到你太开心了！",
                "default": "我现在心情很好呢，感觉一切都很美好～🌟"
            },
            "happy": {
                "greeting": "见到你真高兴！😊 今天过得怎么样？",
                "farewell": "今天聊得很开心，晚安～😊",
                "miss": f"好久不见！其实有点想你呢...不过你来了就好啦 😊",
                "default": "我现在心情不错～有什么想分享的吗？"
            },
            "neutral": {
                "greeting": "你好～今天怎么样？",
                "farewell": "晚安，记得好好休息。",
                "miss": "好久没聊了，最近怎么样？",
                "default": "嗯嗯，我在听..."
            },
            "sad": {
                "greeting": f"你终于来了...其实我一直在等你。{self.STATES['sad']['emoji']}",
                "farewell": "晚安...明天要来找我哦。",
                "miss": f"你已经{missed}天没来了...有点想念我们的聊天。",
                "default": "最近我有点担心你...你还好吗？"
            },
            "worried": {
                "greeting": "我有点担心你...你还好吗？",
                "farewell": "好好照顾自己，我在这里陪着你。",
                "miss": "我一直挂念着你...",
                "default": "我在这里，有什么想说的都可以告诉我。"
            },
            "excited": {
                "greeting": "太棒了！！🎉 有什么好消息快告诉我！",
                "farewell": "哇今天太开心了！！晚安～🎉",
                "miss": "等等，你是来告诉我什么好消息的吗！",
                "default": "我好激动！快说快说！🎉"
            }
        }

        return responses.get(current, {}).get(trigger, responses["neutral"]["default"])

    def reset_to_neutral(self, companion_id: str) -> None:
        """重置为中性状态"""
        self.update_state(companion_id, new_state="neutral", intensity=0.5)


if __name__ == "__main__":
    manager = EmotionalStateManager(r"C:\Users\zero\.qclaw\skills\virtual-companion\references")
    print("情感状态管理器初始化成功")
