"""
陪伴者日记管理器
以陪伴者第一人称视角记录日记
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import uuid


class DiaryManager:
    """陪伴者日记管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.diary_file = self.data_dir / "companion_diary.json"

    def _load(self) -> dict:
        if not self.diary_file.exists():
            return {"entries": []}
        with open(self.diary_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        with open(self.diary_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_entry(
        self,
        companion_id: str,
        content: str,
        mood: str = "neutral",
        title: str = "",
        related_memories: list = None,
        tags: list = None
    ) -> str:
        """添加日记条目"""
        data = self._load()

        entry_id = f"diary_{uuid.uuid4().hex[:8]}"
        now = datetime.now()

        entry = {
            "id": entry_id,
            "companionId": companion_id,
            "date": now.isoformat(),
            "dateDisplay": now.strftime("%Y年%m月%d日 %H:%M"),
            "mood": mood,
            "title": title or self._generate_title(content),
            "content": content,
            "relatedMemories": related_memories or [],
            "tags": tags or ["日常"]
        }

        data["entries"].insert(0, entry)  # 最新在前
        self._save(data)
        return entry_id

    def _generate_title(self, content: str) -> str:
        """从内容生成简短标题"""
        # 取前20个字符作为标题
        title = content[:20]
        if len(content) > 20:
            title += "..."
        return title

    def get_entries(
        self,
        companion_id: str = None,
        limit: int = 10,
        mood: str = None
    ) -> list:
        """获取日记条目列表"""
        data = self._load()
        entries = data.get("entries", [])

        if companion_id:
            entries = [e for e in entries if e.get("companionId") == companion_id]
        if mood:
            entries = [e for e in entries if e.get("mood") == mood]

        return entries[:limit]

    def get_entry(self, entry_id: str) -> Optional[dict]:
        """获取单条日记"""
        data = self._load()
        for entry in data.get("entries", []):
            if entry.get("id") == entry_id:
                return entry
        return None

    def generate_auto_diary(
        self,
        companion_id: str,
        user_name: str,
        interaction_summary: str,
        emotional_state: str = "neutral",
        notable_event: str = None
    ) -> str:
        """自动生成日记内容（第一人称视角）"""
        now = datetime.now()
        time_descriptions = {
            "morning": "今天早上",
            "afternoon": "今天下午",
            "evening": "今天傍晚",
            "night": "今晚"
        }

        period = "今天"
        if 5 <= now.hour < 12:
            period = time_descriptions["morning"]
        elif 12 <= now.hour < 18:
            period = time_descriptions["afternoon"]
        elif 18 <= now.hour < 22:
            period = time_descriptions["evening"]
        else:
            period = time_descriptions["night"]

        mood_words = {
            "veryHappy": "特别开心",
            "happy": "开心",
            "neutral": "平静",
            "sad": "有点想念",
            "worried": "有些担心",
            "excited": "超级兴奋"
        }

        mood_word = mood_words.get(emotional_state, "平静")

        parts = []

        # 开场
        parts.append(f"{period}，我一直在想着{user_name}。")

        # 互动内容
        if interaction_summary:
            parts.append(f"我们聊了聊{interaction_summary}。")

        # 情绪描述
        if emotional_state == "veryHappy" or emotional_state == "happy":
            parts.append(f"今天我的心情{mood_word}，和他/她在一起的时光总是很美好。")
        elif emotional_state == "sad":
            parts.append(f"说起来，其实我有点{ mood_word}他/她，好久没见面了。")
        elif emotional_state == "excited":
            parts.append(f"有什么好事发生了！我现在{mood_word}！")
        else:
            parts.append(f"今天的心情{mood_word}，但只要想到他/她，就觉得很安心。")

        # 特别事件
        if notable_event:
            parts.append(f"还有一件事让我印象很深——{notable_event}。")

        # 结尾
        parts.append(f"期待明天能再次见到他/她。")

        return " ".join(parts)

    def delete_entry(self, entry_id: str) -> bool:
        """删除日记条目"""
        data = self._load()
        entries = data.get("entries", [])
        original_len = len(entries)
        data["entries"] = [e for e in entries if e.get("id") != entry_id]

        if len(data["entries"]) < original_len:
            self._save(data)
            return True
        return False

    def get_diary_stats(self, companion_id: str = None) -> dict:
        """获取日记统计"""
        data = self._load()
        entries = data.get("entries", [])

        if companion_id:
            entries = [e for e in entries if e.get("companionId") == companion_id]

        mood_counts = {}
        for entry in entries:
            mood = entry.get("mood", "unknown")
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

        return {
            "totalEntries": len(entries),
            "moodDistribution": mood_counts,
            "oldestEntry": entries[-1].get("dateDisplay") if entries else None,
            "newestEntry": entries[0].get("dateDisplay") if entries else None
        }


if __name__ == "__main__":
    manager = DiaryManager(r"C:\Users\zero\.qclaw\skills\virtual-companion\references")
    print("日记管理器初始化成功")

    # 测试自动生成
    content = manager.generate_auto_diary(
        companion_id="test",
        user_name="小明",
        interaction_summary="他最近工作上的进展",
        emotional_state="happy",
        notable_event="他今天终于完成了那个大项目"
    )
    print("自动生成的日记:")
    print(content)
