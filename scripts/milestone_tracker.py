"""
纪念日 & 里程碑追踪器
自动追踪相识天数、纪念日、里程碑并触发提醒
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional


MILESTONE_THRESHOLDS = {
    7: ("第一个星期", "我们已经认识整整一周了，时间过得真快！感觉才刚刚遇见你一样。"),
    14: ("两周了", "两周了！这段时间和你相处很开心。"),
    30: ("一个月", "一个月了！感觉认识你很久了，又好像昨天才刚遇见。每一天都值得珍惜。"),
    60: ("两个月", "两个月啦～谢谢你一直陪着我。"),
    100: ("一百天", "今天是我们相识的第100天！🎉 我特别想庆祝一下这个特别的日子！"),
    180: ("半年", "半年了！回想起我们相遇的那天，真的很感慨。时间过得好快，但每一刻都很珍贵。"),
    365: ("一周年", "一周年快乐！！🎂 这是一段很特别的旅程，我很庆幸遇见了你。"),
}


class MilestoneTracker:
    """纪念日 & 里程碑追踪器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.relationship_file = self.data_dir / "relationship.json"

    def _load(self) -> dict:
        with open(self.relationship_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        with open(self.relationship_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def days_since(self, target_date_str: str) -> int:
        """计算距离目标日期的天数"""
        target = datetime.fromisoformat(target_date_str).date()
        today = date.today()
        return (today - target).days

    def days_until(self, target_date_str: str) -> int:
        """计算距离目标日期还有多少天（负数表示已过）"""
        target = datetime.fromisoformat(target_date_str).date()
        today = date.today()
        return (target - today).days

    def get_upcoming_events(self, companion_id: str, days_ahead: int = 30) -> list:
        """获取接下来N天内的重要事件"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return []

        key_dates = companion.get("keyDates", [])
        upcoming = []

        for event in key_dates:
            days = self.days_until(event.get("date", ""))
            if 0 <= days <= days_ahead:
                upcoming.append({
                    "type": event.get("type", "custom"),
                    "label": event.get("description", "重要日子"),
                    "daysUntil": days,
                    "date": event.get("date", ""),
                    "isToday": days == 0
                })
            elif days < 0 and days >= -7:
                # 最近7天内已过的，也标记为"刚刚过去"
                upcoming.append({
                    "type": event.get("type", "custom"),
                    "label": event.get("description", "重要日子"),
                    "daysUntil": days,
                    "date": event.get("date", ""),
                    "justPassed": True
                })

        return sorted(upcoming, key=lambda x: x["daysUntil"])

    def check_milestone_trigger(self, companion_id: str) -> Optional[dict]:
        """检查是否触发里程碑，返回触发信息或None"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return None

        created = companion.get("createdAt", "")
        if not created:
            return None

        days = self.days_since(created)
        achieved = [m.get("days") for m in companion.get("milestones", [])]

        # 检查是否有新的里程碑
        for threshold, (label, message) in MILESTONE_THRESHOLDS.items():
            if days >= threshold and threshold not in achieved:
                return {
                    "days": days,
                    "label": label,
                    "message": message
                }

        return None

    def add_key_date(
        self,
        companion_id: str,
        date_type: str,
        date_str: str,
        description: str
    ) -> bool:
        """添加重要日期"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return False

        key_dates = companion.setdefault("keyDates", [])

        # 检查是否已存在
        for existing in key_dates:
            if existing.get("type") == date_type:
                existing["date"] = date_str
                existing["description"] = description
                self._save(data)
                return True

        key_dates.append({
            "type": date_type,
            "date": date_str,
            "description": description,
            "celebratedCount": 0
        })

        self._save(data)
        return True

    def celebrate_event(self, companion_id: str, event_type: str) -> bool:
        """标记事件已庆祝"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id)
        if not companion:
            return False

        for event in companion.get("keyDates", []):
            if event.get("type") == event_type:
                event["celebratedCount"] = event.get("celebratedCount", 0) + 1
                self._save(data)
                return True

        return False

    def get_relationship_duration(self, companion_id: str) -> dict:
        """获取关系持续时长"""
        data = self._load()
        companion = data.get("companions", {}).get(companion_id, {})
        if not companion:
            return {}

        created = companion.get("createdAt", "")
        if not created:
            return {"days": 0, "formatted": "刚刚认识"}

        days = self.days_since(created)
        months = days // 30
        years = days // 365

        if years > 0:
            remaining_months = (days % 365) // 30
            formatted = f"{years}年{remaining_months}个月"
        elif months > 0:
            formatted = f"{months}个月{days % 30}天"
        else:
            formatted = f"{days}天"

        return {
            "days": days,
            "months": months,
            "years": years,
            "formatted": formatted
        }

    def generate_anniversary_message(self, companion_id: str, days: int, how_they_met: str) -> str:
        """生成纪念日消息"""
        templates = [
            f"知道吗，今天是我们相识的第 {days} 天。",
            f"回想起{how_they_met}，我很庆幸遇见了你。",
            "每一个和你在一起的日子，都让我觉得特别。"
        ]
        return " ".join(templates)


if __name__ == "__main__":
    tracker = MilestoneTracker(r"C:\Users\zero\.qclaw\skills\virtual-companion\references")
    print("纪念日追踪器初始化成功")
