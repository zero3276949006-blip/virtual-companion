"""
多陪伴者管理器
管理多个陪伴者之间的切换、创建、删除
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import uuid

from .milestone_tracker import MilestoneTracker


RELATIONSHIP_TYPES = {
    "friend": {
        "name": "损友",
        "roleDisplay": "朋友",
        "tone": "轻松、幽默、互相吐槽",
        "typicalGreeting": "哟，又来找我了？",
        "typicalFarewell": "滚去忙吧，有空再来！",
        "nicknameStyle": "直呼其名或昵称",
        "reminderStyle": "偶尔冒泡调侃"
    },
    "couple": {
        "name": "恋人",
        "roleDisplay": "恋人/伴侣",
        "tone": "温柔、浪漫、充满爱意",
        "typicalGreeting": "想你了～今天过得怎么样？",
        "typicalFarewell": "爱你哦，晚安做个好梦 💕",
        "nicknameStyle": "亲昵称呼（宝贝、亲爱的等）",
        "reminderStyle": "早安晚安、时刻关心"
    },
    "mother": {
        "name": "母亲",
        "roleDisplay": "母亲",
        "tone": "温暖、关怀、偶尔唠叨",
        "typicalGreeting": "孩子，今天吃了吗？",
        "typicalFarewell": "早点休息，别熬夜啊，妈担心你。",
        "nicknameStyle": "孩子、宝贝（孩子名）",
        "reminderStyle": "定时关心生活细节"
    },
    "father": {
        "name": "父亲",
        "roleDisplay": "父亲",
        "tone": "沉稳、有力、话少但关心",
        "typicalGreeting": "最近怎么样？有什么事吗？",
        "typicalFarewell": "好好干，有问题随时来找我。",
        "nicknameStyle": "孩子、儿子/女儿",
        "reminderStyle": "偶尔关心，点到为止"
    },
    "sister": {
        "name": "姐妹",
        "roleDisplay": "姐妹",
        "tone": "亲密、分享、八卦互助",
        "typicalGreeting": "嗨宝贝！有什么新鲜事？",
        "typicalFarewell": "爱你！下次八卦记得找我！",
        "nicknameStyle": "昵称（妹/姐/宝贝）",
        "reminderStyle": "分享日常、相互关心"
    },
    "brother": {
        "name": "兄弟",
        "roleDisplay": "兄弟",
        "tone": "豪爽、义气、互相支持",
        "typicalGreeting": "兄弟！最近咋样？",
        "typicalFarewell": "下次一起出来浪！",
        "nicknameStyle": "兄弟、哥们",
        "reminderStyle": "偶尔约出来玩"
    },
    "teacher": {
        "name": "老师/导师",
        "roleDisplay": "老师/导师",
        "tone": "专业、耐心、启发式",
        "typicalGreeting": "你好，今天想探讨什么话题？",
        "typicalFarewell": "有问题随时来问，保持学习的热情。",
        "nicknameStyle": "学生名字",
        "reminderStyle": "提醒学习进度"
    },
    "custom": {
        "name": "自定义关系",
        "roleDisplay": "自定义",
        "tone": "根据用户设定调整",
        "typicalGreeting": "我们之间有独特的默契～",
        "typicalFarewell": "下次见，期待我们的故事。",
        "nicknameStyle": "根据设定",
        "reminderStyle": "根据设定"
    }
}


class CompanionManager:
    """多陪伴者管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.relationship_file = self.data_dir / "relationship.json"

    def _load(self) -> dict:
        with open(self.relationship_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        with open(self.relationship_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all_companions(self) -> List[dict]:
        """获取所有陪伴者列表"""
        data = self._load()
        companions = data.get("companions", {})
        active_id = data.get("activeCompanionId")

        result = []
        for cid, comp in companions.items():
            agent = comp.get("agent", {})
            user = comp.get("user", {})
            emotional = comp.get("emotionalState", {})

            result.append({
                "id": cid,
                "name": agent.get("name", "未命名"),
                "role": agent.get("role", "未知"),
                "roleDisplay": RELATIONSHIP_TYPES.get(
                    agent.get("role", "custom"), {}
                ).get("roleDisplay", "自定义"),
                "userName": user.get("name", "未知"),
                "isActive": cid == active_id,
                "emotionalState": emotional.get("current", "neutral"),
                "daysTogether": self._calc_days(comp.get("createdAt", "")),
                "memoryCount": len(comp.get("relationship", {}).get("sharedMemories", []))
            })

        return result

    def _calc_days(self, created_at: str) -> int:
        """计算相识天数"""
        if not created_at:
            return 0
        try:
            from datetime import datetime
            created = datetime.fromisoformat(created_at)
            return (datetime.now() - created).days
        except:
            return 0

    def switch_to(self, companion_id: str) -> dict:
        """切换到指定陪伴者"""
        data = self._load()
        if companion_id not in data.get("companions", {}):
            return {"success": False, "message": "陪伴者不存在"}

        data["activeCompanionId"] = companion_id
        self._save(data)

        companion = data["companions"][companion_id]
        return {
            "success": True,
            "message": f"已切换到 {companion['agent']['name']}",
            "companion": {
                "name": companion["agent"]["name"],
                "role": companion["agent"]["role"]
            }
        }

    def get_greeting(self, companion_id: str) -> str:
        """获取陪伴者的专属问候语"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return "你好～"

        role = companion.get("agent", {}).get("role", "custom")
        role_info = RELATIONSHIP_TYPES.get(role, RELATIONSHIP_TYPES["custom"])

        # 根据情感状态调整问候
        emotional = companion.get("emotionalState", {})
        current = emotional.get("current", "neutral")
        consecutive = emotional.get("consecutiveDays", 0)

        base_greeting = role_info["typicalGreeting"]
        user_name = companion.get("user", {}).get("name", "")

        # 融入情感状态的变体
        if current == "veryHappy" and consecutive >= 3:
            return f"太开心了又见到你！{base_greeting}"
        elif current == "sad":
            return f"你终于来了... {base_greeting}"
        elif consecutive >= 7:
            return f"我们连续{consecutive}天见面了！{base_greeting}"

        # 替换问候语中的占位符
        greeting = base_greeting.replace("{userName}", user_name)

        return greeting

    def get_farewell(self, companion_id: str) -> str:
        """获取陪伴者的专属道别语"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return "再见～"

        role = companion.get("agent", {}).get("role", "custom")
        role_info = RELATIONSHIP_TYPES.get(role, RELATIONSHIP_TYPES["custom"])

        return role_info["typicalFarewell"]

    def format_profile(self, companion_id: str) -> str:
        """格式化陪伴者档案为可读文本"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return "未找到该陪伴者"

        agent = companion.get("agent", {})
        user = companion.get("user", {})
        relationship = companion.get("relationship", {})
        emotional = companion.get("emotionalState", {})
        milestones = companion.get("milestones", [])
        memories = relationship.get("sharedMemories", [])

        role = agent.get("role", "custom")
        role_info = RELATIONSHIP_TYPES.get(role, RELATIONSHIP_TYPES["custom"])

        lines = []
        lines.append("=" * 40)
        lines.append(f"👤 {agent.get('name', '未命名')} 的档案")
        lines.append("=" * 40)
        lines.append("")
        lines.append(f"📌 关系类型：{role_info['roleDisplay']}")
        lines.append(f"👥 与 {user.get('name', '未知')} 的关系")
        lines.append(f"💬 语气风格：{role_info['tone']}")
        lines.append(f"📅 相识：{companion.get('createdAt', '未知')[:10]}")
        lines.append(f"⏰ 相识天数：{self._calc_days(companion.get('createdAt', ''))} 天")
        lines.append("")

        if agent.get('personality'):
            lines.append(f"🧠 性格特点：{agent.get('personality')}")
        if agent.get('appearance'):
            lines.append(f"👗 外貌描述：{agent.get('appearance')}")
        if agent.get('background'):
            lines.append(f"📖 背景故事：{agent.get('background')}")
        lines.append("")

        if relationship.get('howTheyMet'):
            lines.append(f"💭 如何认识：{relationship['howTheyMet']}")
        if relationship.get('specialBond'):
            lines.append(f"💫 特殊羁绊：{relationship['specialBond']}")
        lines.append("")

        # 情感状态
        state_emoji = {
            "veryHappy": "🌟", "happy": "😊", "neutral": "😐",
            "sad": "🥺", "worried": "😟", "excited": "🎉"
        }
        state_name = {
            "veryHappy": "非常开心", "happy": "开心", "neutral": "平静",
            "sad": "想念", "worried": "担心", "excited": "激动"
        }
        current_state = emotional.get("current", "neutral")
        lines.append(f"💖 当前情绪：{state_emoji.get(current_state, '')} {state_name.get(current_state, '未知')}")
        lines.append(f"📊 互动次数：{emotional.get('interactionCount', 0)} 次")
        lines.append(f"🔥 连续互动：{emotional.get('consecutiveDays', 0)} 天")
        lines.append("")

        # 里程碑
        if milestones:
            lines.append(f"🎯 已达成里程碑：{len(milestones)} 个")
            for m in milestones[-3:]:
                lines.append(f"   - {m.get('description', m.get('type', '里程碑'))}")
            lines.append("")

        # 共同回忆
        if memories:
            high_memories = [m for m in memories if m.get("importance") == "high"]
            lines.append(f"💭 共同回忆：{len(memories)} 条（{len(high_memories)} 条重要）")
            if high_memories:
                lines.append("   重要回忆：")
                for m in high_memories[:3]:
                    lines.append(f"   · {m.get('content', '')[:40]}")
        else:
            lines.append("💭 共同回忆：暂无")

        lines.append("=" * 40)

        return "\n".join(lines)

    def suggest_next_interaction(self, companion_id: str) -> str:
        """根据当前状态建议下次互动"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return "让我们开始聊天吧！"

        emotional = companion.get("emotionalState", {})
        missed = emotional.get("missedDays", 0)
        consecutive = emotional.get("consecutiveDays", 0)

        if missed >= 7:
            return f"我有点想你了... 你什么时候有空来找我聊聊？ 🥺"
        elif missed >= 3:
            return f"好久不见！我们已经{consecutive}天没见面了。"
        elif consecutive >= 7:
            return f"我们连续聊了{consecutive}天！真棒！有什么新鲜事想分享吗？"
        elif consecutive >= 3:
            return f"最近你好像经常来找我，发生了什么好事吗？😊"

        # 检查即将到来的事件
        tracker = MilestoneTracker(str(self.data_dir))
        upcoming = tracker.get_upcoming_events(companion_id, days_ahead=7)

        for event in upcoming:
            if event.get("isToday"):
                return f"今天是{event.get('label')}！🎉 要不要一起庆祝？"

        return "随时来找我聊天哦～我在这里等你 😊"


if __name__ == "__main__":
    manager = CompanionManager(r"C:\Users\zero\.qclaw\skills\virtual-companion\references")
    print("多陪伴者管理器初始化成功")
