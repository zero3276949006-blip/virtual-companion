"""
聊天记录导入与分析系统
支持微信、QQ、通用格式的聊天记录导入，自动解析、选择性过滤、深度分析
"""

import json
import os
import re
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from collections import Counter
import uuid


class ChatParser:
    """多格式聊天记录解析器"""

    # 微信导出格式常见分隔符
    WECHAT_PATTERNS = [
        # 微信聊天记录导出格式: 2024-01-15 10:30:22 张三\n消息内容
        re.compile(
            r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+([^\n]+)\n(.+?)(?=\n\d{4}[-/]\d{1,2}|\Z)',
            re.MULTILINE | re.DOTALL
        ),
        # 格式: [2024-01-15 10:30:22] 张三: 消息
        re.compile(
            r'\[(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:\]]+)[：:]\s*(.+?)(?=\[\d{4}|\Z)',
            re.MULTILINE | re.DOTALL
        ),
        # 格式: 张三 2024/1/15 10:30:22\n消息
        re.compile(
            r'^([^\d\n]+?)\s+(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\n(.+?)(?=^\S+\s+\d{4}|\Z)',
            re.MULTILINE | re.DOTALL
        ),
    ]

    # QQ 导出格式常见模式
    QQ_PATTERNS = [
        # QQ导出: 2024-01-15 10:30:22 张三\n消息内容
        re.compile(
            r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+([^\n]+)\n(.+?)(?=\n\d{4}|\Z)',
            re.MULTILINE | re.DOTALL
        ),
        # QQ消息格式: 消息对象:张三\n时间:2024-01-15 10:30:22\n消息:内容
        re.compile(
            r'消息对象[：:]\s*(.+?)\n时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\n消息[：:]\s*(.+?)(?=消息对象|\Z)',
            re.MULTILINE | re.DOTALL
        ),
    ]

    # 通用格式：每行 "时间 发送者: 消息"
    GENERIC_PATTERNS = [
        re.compile(
            r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+([^：:\n]+)[：:]\s*(.+?)$',
            re.MULTILINE
        ),
        re.compile(
            r'^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+([^：:\n]+)[：:]\s*(.+?)$',
            re.MULTILINE
        ),
    ]

    @staticmethod
    def detect_format(file_path: str, content: str = None) -> str:
        """自动检测文件格式

        Returns:
            'json', 'csv', 'wechat_txt', 'qq_txt', 'generic_txt', 'unknown'
        """
        path = Path(file_path)

        # 1. 按扩展名判断
        ext = path.suffix.lower()
        if ext == '.json':
            try:
                if content is None:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                data = json.loads(content)
                # 判断是否微信/QQ导出的JSON
                if isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    if 'type' in first and 'content' in first:
                        return 'wechat_json'
                    if 'sender' in first or 'msg' in first:
                        return 'qq_json'
                return 'json'
            except (json.JSONDecodeError, IOError):
                pass

        if ext == '.csv':
            return 'csv'

        # 2. 按内容判断
        if content is None:
            try:
                for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030']:
                    try:
                        with open(file_path, 'r', encoding=enc) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
            except IOError:
                return 'unknown'

        if not content:
            return 'unknown'

        # 检测JSON
        content_stripped = content.strip()
        if content_stripped.startswith('[') or content_stripped.startswith('{'):
            try:
                json.loads(content)
                return 'json'
            except json.JSONDecodeError:
                pass

        # 检测微信特征
        wechat_markers = ['微信聊天记录', 'Chat History', 'WeChat', '聊天记录导出']
        if any(m in content[:500] for m in wechat_markers):
            return 'wechat_txt'

        # 检测QQ特征
        qq_markers = ['QQ聊天记录', '消息对象', 'QQ Message', '腾讯QQ']
        if any(m in content[:500] for m in qq_markers):
            return 'qq_txt'

        # 尝试匹配通用格式
        for pattern in ChatParser.GENERIC_PATTERNS:
            if pattern.search(content[:2000]):
                return 'generic_txt'

        # 有时间戳和冒号的特征
        if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', content[:1000]) and ':' in content[:500]:
            return 'generic_txt'

        return 'unknown'

    @staticmethod
    def parse_file(file_path: str, source: str = 'auto') -> List[Dict]:
        """解析聊天记录文件，返回标准化的消息列表

        Args:
            file_path: 文件路径
            source: 来源标识 'auto'|'wechat'|'qq'|'generic'

        Returns:
            标准化消息列表: [{"timestamp": "...", "sender": "...", "content": "...", "source": "..."}]
        """
        # 读取文件内容
        content = None
        try:
            for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
        except IOError as e:
            print(f"无法读取文件: {e}")
            return []

        if not content:
            return []

        # 自动检测格式
        fmt = ChatParser.detect_format(file_path, content)

        # 根据用户指定来源和检测格式选择解析方式
        if source != 'auto':
            fmt = f"{source}_{fmt}" if fmt in ('json', 'csv', 'txt') else fmt

        # 分发解析
        if fmt == 'json' or fmt == 'wechat_json':
            return ChatParser._parse_json(content, 'wechat')
        elif fmt == 'qq_json':
            return ChatParser._parse_json(content, 'qq')
        elif fmt == 'csv':
            return ChatParser._parse_csv(file_path)
        elif fmt in ('wechat_txt', 'qq_txt'):
            return ChatParser._parse_txt(content, fmt.split('_')[0])
        elif fmt == 'generic_txt':
            return ChatParser._parse_txt(content, 'generic')
        else:
            # 尝试所有解析方式
            messages = ChatParser._parse_txt(content, 'wechat')
            if not messages:
                messages = ChatParser._parse_txt(content, 'qq')
            if not messages:
                messages = ChatParser._parse_txt(content, 'generic')
            return messages

    @staticmethod
    def _parse_json(content: str, source: str) -> List[Dict]:
        """解析JSON格式聊天记录"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        messages = []

        if isinstance(data, list):
            for item in data:
                msg = ChatParser._normalize_json_msg(item, source)
                if msg:
                    messages.append(msg)
        elif isinstance(data, dict):
            # 可能是嵌套结构
            for key in ['messages', 'data', 'records', 'chat_history', 'msgList']:
                if key in data:
                    items = data[key]
                    if isinstance(items, list):
                        for item in items:
                            msg = ChatParser._normalize_json_msg(item, source)
                            if msg:
                                messages.append(msg)
                    break

            # 微信导出的特殊结构 (内容是字符串包裹的JSON)
            if not messages and 'content' in data and isinstance(data['content'], str):
                try:
                    inner = json.loads(data['content'])
                    if isinstance(inner, list):
                        for item in inner:
                            msg = ChatParser._normalize_json_msg(item, source)
                            if msg:
                                messages.append(msg)
                except json.JSONDecodeError:
                    pass

        return messages

    @staticmethod
    def _normalize_json_msg(item: dict, source: str) -> Optional[Dict]:
        """将各种JSON消息格式标准化"""
        if not isinstance(item, dict):
            return None

        # 微信格式
        if source == 'wechat' or 'CreateTime' in item or 'talker' in item:
            timestamp = item.get('CreateTime') or item.get('createTime') or item.get('timestamp')
            sender = item.get('talker') or item.get('sender') or item.get('from') or item.get('nickName')
            content = item.get('content') or item.get('text') or item.get('msg') or ''
            msg_type = item.get('type', 1)

            # 只保留文本消息
            if isinstance(msg_type, int) and msg_type != 1:
                return None

        # QQ格式
        elif source == 'qq' or 'sender' in item or 'uin' in item:
            timestamp = item.get('time') or item.get('timestamp') or item.get('msgTime')
            sender_info = item.get('sender', {})
            if isinstance(sender_info, dict):
                sender = sender_info.get('nickname') or sender_info.get('name') or str(sender_info.get('uin', ''))
            else:
                sender = str(sender_info) if sender_info else ''
            content = item.get('content') or item.get('text') or item.get('msg') or item.get('rawContent') or ''

        else:
            # 通用格式
            timestamp = item.get('timestamp') or item.get('time') or item.get('date') or item.get('datetime')
            sender = item.get('sender') or item.get('from') or item.get('user') or item.get('name') or ''
            content = item.get('content') or item.get('text') or item.get('message') or item.get('msg') or ''

        # 格式化时间戳
        if isinstance(timestamp, (int, float)):
            try:
                ts = datetime.fromtimestamp(timestamp)
                timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')
            except (OSError, ValueError):
                timestamp = str(timestamp)

        # 清理内容
        content = str(content).strip()
        # 过滤系统消息
        if not content or content.startswith('---') or content == '[图片]' or content == '[语音]':
            return None

        return {
            "timestamp": str(timestamp) if timestamp else '',
            "sender": str(sender).strip(),
            "content": content,
            "source": source
        }

    @staticmethod
    def _parse_csv(file_path: str) -> List[Dict]:
        """解析CSV格式聊天记录"""
        messages = []
        try:
            for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030']:
                try:
                    with open(file_path, 'r', encoding=enc, newline='') as f:
                        # 尝试检测分隔符
                        sample = f.read(4096)
                        f.seek(0)
                        dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
                        reader = csv.DictReader(f, dialect=dialect)
                        rows = list(reader)

                    if not rows:
                        continue

                    # 自动映射字段名
                    field_map = ChatParser._detect_csv_fields(rows[0])
                    if not field_map:
                        continue

                    for row in rows:
                        timestamp = row.get(field_map.get('timestamp', ''), '')
                        sender = row.get(field_map.get('sender', ''), '')
                        content = row.get(field_map.get('content', ''), '')

                        if content:
                            messages.append({
                                "timestamp": str(timestamp).strip(),
                                "sender": str(sender).strip(),
                                "content": str(content).strip(),
                                "source": "csv"
                            })

                    break
                except (UnicodeDecodeError, csv.Error):
                    continue

        except IOError:
            pass

        return messages

    @staticmethod
    def _detect_csv_fields(sample_row: dict) -> Optional[Dict]:
        """自动检测CSV字段映射

        Returns:
            {'timestamp': '字段名', 'sender': '字段名', 'content': '字段名'}
        """
        field_map = {}
        keys = [k.lower().strip() for k in sample_row.keys()]

        # 时间字段
        time_keys = ['时间', 'time', 'timestamp', 'datetime', 'date', '日期', '发送时间', 'msg_time', 'created_at']
        for k in time_keys:
            if k in keys:
                field_map['timestamp'] = sample_row.keys()[keys.index(k)]
                break

        # 发送者字段
        sender_keys = ['发送者', 'sender', 'name', 'nick', 'nickname', 'user', 'from', '用户', '发言人', 'talker']
        for k in sender_keys:
            if k in keys:
                field_map['sender'] = sample_row.keys()[keys.index(k)]
                break

        # 内容字段
        content_keys = ['内容', 'content', 'text', 'message', 'msg', '消息', '正文', 'raw_content', 'body']
        for k in content_keys:
            if k in keys:
                field_map['content'] = sample_row.keys()[keys.index(k)]
                break

        return field_map if len(field_map) >= 2 else None

    @staticmethod
    def _parse_txt(content: str, source: str) -> List[Dict]:
        """解析文本格式聊天记录"""
        messages = []

        # 选择匹配模式
        if source == 'wechat':
            patterns = ChatParser.WECHAT_PATTERNS
        elif source == 'qq':
            patterns = ChatParser.QQ_PATTERNS
        else:
            patterns = ChatParser.GENERIC_PATTERNS + ChatParser.WECHAT_PATTERNS + ChatParser.QQ_PATTERNS

        best_matches = []
        for pattern in patterns:
            matches = list(pattern.finditer(content))
            if len(matches) > len(best_matches):
                best_matches = matches

        for match in best_matches:
            groups = match.groups()
            if len(groups) >= 3:
                timestamp, sender, msg_content = groups[0], groups[1], groups[2]
            elif len(groups) == 2:
                # QQ特殊格式：sender, timestamp
                sender, timestamp = groups[0], groups[1]
                msg_content = ''
            else:
                continue

            msg_content = msg_content.strip()
            # 清理：去掉系统消息、空白
            if not msg_content or msg_content.startswith('---') or msg_content.startswith('==='):
                continue
            if msg_content in ('[图片]', '[语音]', '[视频]', '[表情]', '[文件]', '[红包]', '[位置]'):
                continue

            # 过滤明显的系统通知
            if re.match(r'^---.*---$', msg_content):
                continue
            if '撤回了一条消息' in msg_content or '加入了群聊' in msg_content:
                continue

            messages.append({
                "timestamp": timestamp.strip(),
                "sender": sender.strip(),
                "content": msg_content,
                "source": source
            })

        # 如果正则没匹配到，尝试按行解析
        if not messages:
            messages = ChatParser._parse_txt_line_by_line(content, source)

        return messages

    @staticmethod
    def _parse_txt_line_by_line(content: str, source: str) -> List[Dict]:
        """逐行解析文本聊天记录（降级方案）"""
        messages = []
        lines = content.split('\n')
        current_msg = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 尝试匹配 "时间 发送者: 内容" 格式
            m = re.match(
                r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+([^：:\n]+)[：:]\s*(.+)',
                line
            )
            if m:
                if current_msg:
                    messages.append(current_msg)
                current_msg = {
                    "timestamp": m.group(1).strip(),
                    "sender": m.group(2).strip(),
                    "content": m.group(3).strip(),
                    "source": source
                }
            else:
                # 可能是上一条消息的续行
                if current_msg and line:
                    current_msg["content"] += "\n" + line

        if current_msg:
            messages.append(current_msg)

        return messages


class ChatFilter:
    """选择性导入过滤器"""

    @staticmethod
    def filter_messages(
        messages: List[Dict],
        start_date: str = None,
        end_date: str = None,
        keywords: List[str] = None,
        exclude_keywords: List[str] = None,
        senders: List[str] = None,
        exclude_system: bool = True,
        min_length: int = 1,
        max_length: int = 5000,
        sensitive_patterns: List[str] = None
    ) -> List[Dict]:
        """过滤消息

        Args:
            messages: 消息列表
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            keywords: 只保留包含这些关键词的消息
            exclude_keywords: 排除包含这些关键词的消息
            senders: 只保留这些发送者的消息
            exclude_system: 排除系统消息
            min_length: 最小消息长度
            max_length: 最大消息长度
            sensitive_patterns: 敏感内容正则模式列表（如手机号、身份证等）
        """
        filtered = []
        sensitive_re = []
        if sensitive_patterns:
            for p in sensitive_patterns:
                try:
                    sensitive_re.append(re.compile(p))
                except re.error:
                    pass

        # 默认敏感模式：手机号、身份证号、银行卡号
        default_sensitive = [
            r'1[3-9]\d{9}',  # 手机号
            r'\d{6}(?:\d{2})?(?:\d{4})?(?:\d{3})?[0-9Xx]',  # 身份证
            r'\d{16,19}',  # 银行卡号
        ]
        if sensitive_patterns is not None and sensitive_patterns:  # 用户提供了自定义敏感模式
            pass  # 用用户提供的
        elif sensitive_patterns is None:  # 默认启用
            for p in default_sensitive:
                sensitive_re.append(re.compile(p))

        for msg in messages:
            # 1. 时间范围过滤
            ts = msg.get('timestamp', '')
            if start_date or end_date:
                try:
                    # 尝试解析时间
                    msg_date = ChatFilter._parse_date(ts)
                    if msg_date:
                        if start_date and msg_date < start_date:
                            continue
                        if end_date and msg_date > end_date:
                            continue
                    elif start_date or end_date:
                        # 无法解析时间且有过滤条件，跳过
                        continue
                except (ValueError, TypeError):
                    if start_date or end_date:
                        continue

            # 2. 关键词过滤
            content = msg.get('content', '')
            if keywords:
                if not any(kw in content for kw in keywords):
                    continue

            # 3. 排除关键词
            if exclude_keywords:
                if any(kw in content for kw in exclude_keywords):
                    continue

            # 4. 发送者过滤
            if senders:
                sender = msg.get('sender', '')
                if not any(s.lower() in sender.lower() for s in senders):
                    continue

            # 5. 系统消息过滤
            if exclude_system:
                if ChatFilter._is_system_message(content):
                    continue

            # 6. 长度过滤
            if len(content) < min_length or len(content) > max_length:
                continue

            # 7. 敏感内容过滤（脱敏）
            if sensitive_re:
                for pattern in sensitive_re:
                    content = pattern.sub('[已脱敏]', content)
                msg = {**msg, "content": content}

            filtered.append(msg)

        return filtered

    @staticmethod
    def _parse_date(timestamp_str: str) -> Optional[str]:
        """尝试从时间字符串中解析出日期 YYYY-MM-DD"""
        if not timestamp_str:
            return None
        # 提取日期部分
        m = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', timestamp_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None

    @staticmethod
    def _is_system_message(content: str) -> bool:
        """判断是否为系统消息"""
        system_markers = [
            '撤回了一条消息', '加入了群聊', '修改了群名', '开启了群禁言',
            '邀请', '加入了群', '移出了群', '成为新群主',
            '你已添加', '以上是', '---', '===',
            '[红包]', '[转账]', '[语音]', '[视频]', '[图片]',
            '领取了红包', '拍了拍'
        ]
        return any(marker in content for marker in system_markers)


class ChatAnalyzer:
    """聊天记录深度分析器"""

    # 情感词库
    POSITIVE_WORDS = [
        '开心', '高兴', '快乐', '幸福', '喜欢', '爱', '爱你', '想你', '想念',
        '哈哈', '嘻嘻', '么么', '亲亲', '抱抱', '宝贝', '亲爱的', '温暖',
        '感动', '好棒', '厉害', '加油', '支持', '可爱', '帅', '美',
        '好呀', '好的', '没问题', '当然', '一定', '必须', '太好了', '棒',
        '❤', '💕', '😘', '🤗', '😊', '😄', '🥰', '😍', '❤️', '💗', '💖', '🎉', '👏',
        '好的呢', '好哒', '嗯嗯', '好滴', '好呀', '嘻嘻嘻', '哈哈哈哈',
        '最好的', '最美', '最棒', '超开心', '超级', '特别', '非常',
    ]

    NEGATIVE_WORDS = [
        '难过', '伤心', '不开心', '郁闷', '烦', '讨厌', '恨', '生气',
        '对不起', '抱歉', '别', '不要', '不想', '不舒服', '累', '困',
        '😭', '😢', '😞', '😔', '😤', '😡', '💔', '😥', '😓',
        '算了', '无所谓', '随便', '不知道', '不想说', '别管',
    ]

    QUIET_WORDS = [
        '嗯', '哦', '好', '行', '是', '对', '嗯嗯', '哦哦',
        '好嘞', '收到', '知道了', '明白', '了解', '懂了',
    ]

    # 称呼/昵称模式
    NICKNAME_PATTERNS = [
        re.compile(r'叫[我你他她]([^\s,.，。!！?？]{1,6})'),
        re.compile(r'[我你他她]是([^\s,.，。!！?？]{1,6})'),
        re.compile(r'昵称[是为]([^\s,.，。!！?？]{1,6})'),
    ]

    @staticmethod
    def analyze(messages: List[Dict], companion_name: str = '', user_name: str = '') -> Dict:
        """深度分析聊天记录

        Returns:
            {
                "dialogStyle": {...},       # 对话风格
                "sharedMemories": [...],    # 共同回忆
                "nicknames": {...},         # 称呼方式
                "emotionalProfile": {...},  # 情感基调
                "frequentTopics": [...],    # 高频话题
                "interactionPatterns": {...},# 互动模式
                "summary": "..."            # 摘要
            }
        """
        if not messages:
            return ChatAnalyzer._empty_analysis()

        # 区分陪伴者和用户的消息
        companion_msgs = []
        user_msgs = []
        for msg in messages:
            sender = msg.get('sender', '')
            if companion_name and companion_name in sender:
                companion_msgs.append(msg)
            elif user_name and user_name in sender:
                user_msgs.append(msg)
            else:
                # 未知发送者，根据上下文猜测
                user_msgs.append(msg)

        analysis = {
            "dialogStyle": ChatAnalyzer._analyze_dialog_style(companion_msgs, user_msgs),
            "sharedMemories": ChatAnalyzer._extract_memories(messages),
            "nicknames": ChatAnalyzer._extract_nicknames(messages, companion_name, user_name),
            "emotionalProfile": ChatAnalyzer._analyze_emotion(messages, companion_msgs, user_msgs),
            "frequentTopics": ChatAnalyzer._extract_topics(messages),
            "interactionPatterns": ChatAnalyzer._analyze_interaction_patterns(messages),
            "stats": ChatAnalyzer._compute_stats(messages, companion_msgs, user_msgs),
            "analyzedAt": datetime.now().isoformat()
        }

        # 生成摘要
        analysis["summary"] = ChatAnalyzer._generate_summary(analysis)

        return analysis

    @staticmethod
    def _empty_analysis() -> Dict:
        return {
            "dialogStyle": {},
            "sharedMemories": [],
            "nicknames": {},
            "emotionalProfile": {},
            "frequentTopics": [],
            "interactionPatterns": {},
            "stats": {},
            "summary": "无有效聊天记录可供分析"
        }

    @staticmethod
    def _analyze_dialog_style(companion_msgs: List[Dict], user_msgs: List[Dict]) -> Dict:
        """分析对话风格"""
        style = {
            "companion": {
                "avgLength": 0,
                "emojiFrequency": 0,
                "questionRate": 0,
                "exclamationRate": 0,
                "commonOpeners": [],
                "commonClosers": [],
                "vibeTags": []
            },
            "user": {
                "avgLength": 0,
                "emojiFrequency": 0,
                "questionRate": 0,
                "exclamationRate": 0,
            },
            "conversationalTone": "",
            "formality": ""
        }

        for role, msgs in [('companion', companion_msgs), ('user', user_msgs)]:
            if not msgs:
                continue

            contents = [m.get('content', '') for m in msgs]
            total = len(contents)

            # 平均消息长度
            style[role]["avgLength"] = round(sum(len(c) for c in contents) / total, 1)

            # 表情符号频率
            emoji_count = sum(len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001f900-\U0001f9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]', c)) for c in contents)
            style[role]["emojiFrequency"] = round(emoji_count / total, 2)

            # 问句比例
            questions = sum(1 for c in contents if '?' in c or '？' in c)
            style[role]["questionRate"] = round(questions / total, 2)

            # 感叹号比例
            exclamations = sum(1 for c in contents if '!' in c or '！' in c)
            style[role]["exclamationRate"] = round(exclamations / total, 2)

        # 陪伴者常用开场/结束语
        if companion_msgs:
            # 取前3条消息的前几个字
            openers = [m.get('content', '')[:10] for m in companion_msgs[:20]]
            closers = [m.get('content', '')[-10:] for m in companion_msgs[-20:]]
            style["companion"]["commonOpeners"] = openers[:5]
            style["companion"]["commonClosers"] = closers[:5]

            # 氛围标签
            vibes = []
            all_content = ' '.join(m.get('content', '') for m in companion_msgs)
            if style["companion"]["emojiFrequency"] > 0.5:
                vibes.append('表情达人')
            if style["companion"]["avgLength"] > 30:
                vibes.append('话多热情')
            elif style["companion"]["avgLength"] < 10:
                vibes.append('简洁干练')
            if style["companion"]["questionRate"] > 0.3:
                vibes.append('关心型')
            if '撒娇' in all_content or '哼' in all_content or '嘛' in all_content:
                vibes.append('撒娇型')
            if '哈哈' in all_content or '笑' in all_content:
                vibes.append('幽默风趣')
            style["companion"]["vibeTags"] = vibes

        # 对话整体基调
        if style["companion"]["emojiFrequency"] > 0.3 and style["user"]["emojiFrequency"] > 0.3:
            style["conversationalTone"] = "轻松活泼"
        elif style["companion"]["avgLength"] < 8 and style["user"]["avgLength"] < 8:
            style["conversationalTone"] = "简洁日常"
        elif style["companion"]["questionRate"] > 0.3:
            style["conversationalTone"] = "关心互动"
        else:
            style["conversationalTone"] = "自然随性"

        # 正式程度
        formal_score = 0
        all_msgs = companion_msgs + user_msgs
        for m in all_msgs:
            c = m.get('content', '')
            if '您' in c:
                formal_score += 2
            if any(w in c for w in ['请问', '麻烦', '劳驾', '感谢']):
                formal_score += 1
        style["formality"] = "正式" if formal_score > 5 else "随意"

        return style

    @staticmethod
    def _extract_memories(messages: List[Dict]) -> List[Dict]:
        """从聊天记录中提取共同回忆"""
        memories = []

        # 关键事件标记词
        event_markers = [
            '生日', '纪念', '在一起', '第一次', '终于', '毕业', '入职',
            '搬家', '旅行', '旅游', '去了', '看到', '见到了',
            '新年', '圣诞', '情人节', '中秋', '国庆', '春节',
            '加班', '升职', '面试', '考试', '通过了', '成功了',
            '买了', '收到', '送给', '惊喜', '感动',
            '吵架', '和好', '分手', '复合',
        ]

        seen_contents = set()
        for msg in messages:
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')

            # 检测是否包含重要事件
            is_important = any(marker in content for marker in event_markers)
            if not is_important:
                continue

            # 去重
            content_hash = hashlib.md5(content[:50].encode()).hexdigest()[:8]
            if content_hash in seen_contents:
                continue
            seen_contents.add(content_hash)

            # 判断重要性
            high_importance_markers = ['生日', '纪念', '第一次', '在一起', '毕业', '升职', '旅行', '旅游', '搬家']
            importance = 'high' if any(m in content for m in high_importance_markers) else 'medium'

            memories.append({
                "id": f"chat_mem_{uuid.uuid4().hex[:8]}",
                "content": content[:200],  # 截断过长内容
                "date": ChatAnalyzer._extract_date(timestamp),
                "importance": importance,
                "source": "chat_import",
                "tags": ChatAnalyzer._extract_tags(content)
            })

        return memories[:50]  # 最多保留50条

    @staticmethod
    def _extract_date(timestamp: str) -> str:
        """从时间戳提取日期"""
        if not timestamp:
            return ''
        m = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', timestamp)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return ''

    @staticmethod
    def _extract_tags(content: str) -> List[str]:
        """从内容中提取标签"""
        tags = []
        tag_keywords = {
            '旅行': ['旅行', '旅游', '去了', '出差'],
            '工作': ['加班', '升职', '面试', '入职', '工作'],
            '学习': ['考试', '毕业', '学习', '读书'],
            '节日': ['新年', '圣诞', '中秋', '春节', '国庆', '情人节'],
            '情感': ['爱你', '想你', '喜欢', '在一起', '吵架', '和好'],
            '日常生活': ['吃饭', '睡觉', '逛街', '看电影'],
            '生日': ['生日'],
            '惊喜': ['惊喜', '感动', '没想到'],
        }
        for tag, keywords in tag_keywords.items():
            if any(kw in content for kw in keywords):
                tags.append(tag)
        return tags[:5]

    @staticmethod
    def _extract_nicknames(messages: List[Dict], companion_name: str, user_name: str) -> Dict:
        """提取称呼方式"""
        nicknames = {
            "companionCallsUser": [],    # 陪伴者对用户的称呼
            "userCallsCompanion": [],    # 用户对陪伴者的称呼
            "detectedPatterns": []       # 检测到的称呼模式
        }

        all_content = ' '.join(m.get('content', '') for m in messages)

        # 常见称呼词库
        affectionate_terms = [
            '宝贝', '亲爱的', '老公', '老婆', '媳妇', '老公公', '老婆婆',
            '哥', '姐', '弟弟', '妹妹', '大哥', '大姐',
            '亲', '亲爱', '乖乖', '宝宝', '小可爱', '大可爱',
            '笨蛋', '傻瓜', '猪猪', '小猪', '大叔',
            '同学', '老师', '老板', '领导',
            '老+[名]', '小+[名]', '阿+[名]',
        ]

        # 通过正则提取称呼
        for msg in messages:
            content = msg.get('content', '')
            sender = msg.get('sender', '')

            # 寻找昵称模式
            for pattern in ChatAnalyzer.NICKNAME_PATTERNS:
                matches = pattern.findall(content)
                for match in matches:
                    if match and len(match) <= 6:
                        nicknames["detectedPatterns"].append({
                            "term": match,
                            "context": content[:50]
                        })

            # 直接匹配亲昵称呼
            for term in affectionate_terms:
                if '[' in term:  # 模式如 "老+[名]"
                    continue
                if term in content:
                    entry = {"term": term, "context": content[:50]}
                    if companion_name and companion_name in sender:
                        if entry not in nicknames["companionCallsUser"]:
                            nicknames["companionCallsUser"].append(entry)
                    elif user_name and user_name in sender:
                        if entry not in nicknames["userCallsCompanion"]:
                            nicknames["userCallsCompanion"].append(entry)

        # 去重截断
        nicknames["companionCallsUser"] = nicknames["companionCallsUser"][:10]
        nicknames["userCallsCompanion"] = nicknames["userCallsCompanion"][:10]
        nicknames["detectedPatterns"] = nicknames["detectedPatterns"][:10]

        return nicknames

    @staticmethod
    def _analyze_emotion(messages: List[Dict], companion_msgs: List[Dict], user_msgs: List[Dict]) -> Dict:
        """分析情感基调"""
        profile = {
            "overallTone": "",           # 总体基调
            "positiveRate": 0,           # 正面情感比例
            "negativeRate": 0,           # 负面情感比例
            "emotionalVolatility": "",   # 情感波动性
            "topEmotionalMoments": [],   # 情感高峰时刻
            "companionEmotionalStyle": "", # 陪伴者情感风格
            "userEmotionalStyle": "",    # 用户情感风格
        }

        total = len(messages)
        if total == 0:
            return profile

        # 统计正负面消息
        positive_count = 0
        negative_count = 0
        emotional_moments = []

        for msg in messages:
            content = msg.get('content', '')
            has_pos = any(w in content for w in ChatAnalyzer.POSITIVE_WORDS)
            has_neg = any(w in content for w in ChatAnalyzer.NEGATIVE_WORDS)

            if has_pos and not has_neg:
                positive_count += 1
            elif has_neg and not has_pos:
                negative_count += 1

            # 记录情感高峰（包含多个情感词的消息）
            pos_count = sum(1 for w in ChatAnalyzer.POSITIVE_WORDS if w in content)
            neg_count = sum(1 for w in ChatAnalyzer.NEGATIVE_WORDS if w in content)
            if pos_count >= 3 or neg_count >= 2:
                emotional_moments.append({
                    "content": content[:100],
                    "date": ChatAnalyzer._extract_date(msg.get('timestamp', '')),
                    "type": "positive" if pos_count > neg_count else "negative"
                })

        profile["positiveRate"] = round(positive_count / total, 2)
        profile["negativeRate"] = round(negative_count / total, 2)
        profile["topEmotionalMoments"] = emotional_moments[:10]

        # 总体基调
        if profile["positiveRate"] > 0.3:
            profile["overallTone"] = "温暖积极"
        elif profile["negativeRate"] > 0.2:
            profile["overallTone"] = "沉稳内敛"
        elif profile["positiveRate"] > profile["negativeRate"]:
            profile["overallTone"] = "温和适度"
        else:
            profile["overallTone"] = "平静自然"

        # 情感波动性
        if profile["positiveRate"] > 0.4 and profile["negativeRate"] > 0.15:
            profile["emotionalVolatility"] = "丰富多变"
        elif profile["positiveRate"] > 0.2:
            profile["emotionalVolatility"] = "稳定积极"
        else:
            profile["emotionalVolatility"] = "平和稳定"

        # 陪伴者情感风格
        if companion_msgs:
            comp_pos = sum(1 for m in companion_msgs if any(w in m.get('content', '') for w in ChatAnalyzer.POSITIVE_WORDS))
            comp_total = len(companion_msgs)
            if comp_total > 0:
                ratio = comp_pos / comp_total
                if ratio > 0.4:
                    profile["companionEmotionalStyle"] = "热情温暖型"
                elif ratio > 0.2:
                    profile["companionEmotionalStyle"] = "温柔细腻型"
                else:
                    profile["companionEmotionalStyle"] = "沉稳内敛型"

        return profile

    @staticmethod
    def _extract_topics(messages: List[Dict]) -> List[Dict]:
        """提取高频话题"""
        # 简单的关键词频率统计
        topic_keywords = {
            '工作': ['工作', '加班', '上班', '下班', '开会', '同事', '领导', '项目', '任务'],
            '生活': ['吃饭', '睡觉', '洗澡', '做饭', '收拾', '打扫'],
            '娱乐': ['游戏', '电影', '音乐', '综艺', '追剧', '动漫'],
            '社交': ['朋友', '聚会', '约', '出来', '一起'],
            '情感': ['想你', '爱你', '喜欢', '开心', '难过', '生气'],
            '健康': ['生病', '医院', '吃药', '锻炼', '减肥', '身体'],
            '美食': ['吃', '喝', '餐厅', '外卖', '火锅', '烧烤', '奶茶'],
            '旅行': ['旅行', '旅游', '出去', '机票', '酒店', '玩'],
            '学习': ['学习', '考试', '读书', '上课', '论文'],
            '购物': ['买', '购物', '淘宝', '快递', '发货', '打折'],
            '家庭': ['家里', '爸妈', '妈妈', '爸爸', '家人', '回家'],
            '天气': ['天气', '下雨', '好热', '好冷', '下雪'],
        }

        all_content = ' '.join(m.get('content', '') for m in messages)
        topic_scores = []

        for topic, keywords in topic_keywords.items():
            score = sum(all_content.count(kw) for kw in keywords)
            if score > 0:
                topic_scores.append({
                    "topic": topic,
                    "score": score,
                    "sampleMessages": [
                        m.get('content', '')[:60]
                        for m in messages
                        if any(kw in m.get('content', '') for kw in keywords)
                    ][:3]
                })

        # 按频率排序
        topic_scores.sort(key=lambda x: x["score"], reverse=True)
        return topic_scores[:10]

    @staticmethod
    def _analyze_interaction_patterns(messages: List[Dict]) -> Dict:
        """分析互动模式"""
        patterns = {
            "avgReplyDelay": "",         # 平均回复延迟（难以精确计算，用估算）
            "conversationStyle": "",     # 对话风格
            "peakHours": [],             # 活跃时段
            "avgMessagesPerDay": 0,      # 日均消息数
            "weekendVsWeekday": "",      # 工作日vs周末
        }

        if not messages:
            return patterns

        # 活跃时段统计
        hour_counts = Counter()
        dates = set()

        for msg in messages:
            ts = msg.get('timestamp', '')
            # 提取小时
            hour_match = re.search(r'(\d{1,2}):\d{2}', ts)
            if hour_match:
                hour = int(hour_match.group(1))
                hour_counts[hour] += 1
            # 提取日期
            date = ChatAnalyzer._extract_date(ts)
            if date:
                dates.add(date)

        # 峰值时段
        if hour_counts:
            peak_hours = hour_counts.most_common(5)
            patterns["peakHours"] = [
                {"hour": h, "count": c} for h, c in peak_hours
            ]

        # 日均消息数
        if dates:
            patterns["avgMessagesPerDay"] = round(len(messages) / max(len(dates), 1), 1)

        # 对话风格
        if patterns["avgMessagesPerDay"] > 50:
            patterns["conversationStyle"] = "高频密聊型"
        elif patterns["avgMessagesPerDay"] > 20:
            patterns["conversationStyle"] = "日常互动型"
        elif patterns["avgMessagesPerDay"] > 5:
            patterns["conversationStyle"] = "适度联系型"
        else:
            patterns["conversationStyle"] = "偶尔联系型"

        return patterns

    @staticmethod
    def _compute_stats(messages: List[Dict], companion_msgs: List[Dict], user_msgs: List[Dict]) -> Dict:
        """计算基本统计"""
        return {
            "totalMessages": len(messages),
            "companionMessages": len(companion_msgs),
            "userMessages": len(user_msgs),
            "dateRange": {
                "start": ChatAnalyzer._extract_date(messages[0].get('timestamp', '')) if messages else '',
                "end": ChatAnalyzer._extract_date(messages[-1].get('timestamp', '')) if messages else '',
            },
            "uniqueSenders": len(set(m.get('sender', '') for m in messages if m.get('sender')))
        }

    @staticmethod
    def _generate_summary(analysis: Dict) -> str:
        """生成分析摘要"""
        parts = []

        stats = analysis.get("stats", {})
        total = stats.get("totalMessages", 0)
        date_range = stats.get("dateRange", {})
        start = date_range.get("start", '未知')
        end = date_range.get("end", '未知')

        parts.append(f"共分析 {total} 条消息，时间跨度 {start} 至 {end}。")

        style = analysis.get("dialogStyle", {})
        tone = style.get("conversationalTone", '')
        if tone:
            parts.append(f"对话整体基调：{tone}。")

        emotion = analysis.get("emotionalProfile", {})
        overall_tone = emotion.get("overallTone", '')
        if overall_tone:
            parts.append(f"情感倾向：{overall_tone}（正面率{emotion.get('positiveRate', 0):.0%}，负面率{emotion.get('negativeRate', 0):.0%}）。")

        topics = analysis.get("frequentTopics", [])
        if topics:
            top_topics = ', '.join(t["topic"] for t in topics[:3])
            parts.append(f"高频话题：{top_topics}。")

        memories = analysis.get("sharedMemories", [])
        if memories:
            parts.append(f"提取到 {len(memories)} 条潜在共同回忆。")

        nicknames = analysis.get("nicknames", {})
        comp_calls = nicknames.get("companionCallsUser", [])
        user_calls = nicknames.get("userCallsCompanion", [])
        if comp_calls:
            terms = ', '.join(c["term"] for c in comp_calls[:3])
            parts.append(f"陪伴者称呼用户：{terms}")
        if user_calls:
            terms = ', '.join(c["term"] for c in user_calls[:3])
            parts.append(f"用户称呼陪伴者：{terms}")

        return ' '.join(parts)


class ChatImporter:
    """聊天记录导入主入口"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.analysis_file = self.data_dir / "chat_analysis.json"
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def import_chat(
        self,
        file_path: str,
        source: str = 'auto',
        companion_name: str = '',
        user_name: str = '',
        # 选择性导入参数
        start_date: str = None,
        end_date: str = None,
        keywords: List[str] = None,
        exclude_keywords: List[str] = None,
        senders: List[str] = None,
        min_length: int = 1,
        max_length: int = 5000,
        sensitive_patterns: List[str] = None,
        disable_auto_sensitive: bool = False,
    ) -> Dict:
        """导入聊天记录的完整流程

        Args:
            file_path: 聊天记录文件路径
            source: 来源 'auto'|'wechat'|'qq'|'generic'
            companion_name: 陪伴者名字（用于区分消息发送者）
            user_name: 用户名字
            start_date: 起始日期过滤
            end_date: 结束日期过滤
            keywords: 关键词过滤（只保留包含的消息）
            exclude_keywords: 排除关键词
            senders: 发送者过滤
            min_length: 最小消息长度
            max_length: 最大消息长度
            sensitive_patterns: 自定义敏感内容正则
            disable_auto_sensitive: 禁用自动敏感内容脱敏

        Returns:
            {
                "success": bool,
                "format": "检测到的格式",
                "totalRaw": 原始消息数,
                "totalFiltered": 过滤后消息数,
                "analysis": 分析结果,
                "message": "状态消息"
            }
        """
        result = {
            "success": False,
            "format": "",
            "totalRaw": 0,
            "totalFiltered": 0,
            "analysis": {},
            "message": ""
        }

        # 1. 检测格式
        fmt = ChatParser.detect_format(file_path)
        result["format"] = fmt

        if fmt == 'unknown':
            result["message"] = f"无法识别文件格式: {file_path}。支持 TXT/CSV/JSON 格式。"
            return result

        # 2. 解析
        messages = ChatParser.parse_file(file_path, source)
        result["totalRaw"] = len(messages)

        if not messages:
            result["message"] = "解析完成但未提取到有效消息。请检查文件格式。"
            return result

        # 3. 过滤
        sp = [] if disable_auto_sensitive else sensitive_patterns
        filtered = ChatFilter.filter_messages(
            messages,
            start_date=start_date,
            end_date=end_date,
            keywords=keywords,
            exclude_keywords=exclude_keywords,
            senders=senders,
            min_length=min_length,
            max_length=max_length,
            sensitive_patterns=sp
        )
        result["totalFiltered"] = len(filtered)

        if not filtered:
            result["message"] = f"原始 {result['totalRaw']} 条消息，过滤后为 0 条。请调整过滤条件。"
            return result

        # 4. 分析
        analysis = ChatAnalyzer.analyze(filtered, companion_name, user_name)
        result["analysis"] = analysis

        # 5. 保存分析结果
        self._save_analysis(analysis)

        # 6. 更新 relationship.json 中的相关数据
        self._update_relationship_data(analysis)

        result["success"] = True
        filter_note = ""
        if result["totalRaw"] != result["totalFiltered"]:
            filter_note = f"（过滤掉了 {result['totalRaw'] - result['totalFiltered']} 条）"
        result["message"] = (
            f"导入成功！格式: {fmt}，原始 {result['totalRaw']} 条消息{filter_note}，"
            f"分析后提取 {len(analysis.get('sharedMemories', []))} 条共同回忆。"
        )

        return result

    def _save_analysis(self, analysis: Dict) -> None:
        """保存分析结果"""
        # 合并已有数据
        existing = {}
        if self.analysis_file.exists():
            try:
                with open(self.analysis_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # 追加而不是覆盖
        if 'imports' not in existing:
            existing['imports'] = []

        existing['imports'].append({
            "id": f"imp_{uuid.uuid4().hex[:8]}",
            "analyzedAt": analysis.get("analyzedAt", datetime.now().isoformat()),
            "summary": analysis.get("summary", ""),
            "stats": analysis.get("stats", {}),
        })

        # 合并分析数据
        if 'dialogStyle' not in existing or not existing['dialogStyle']:
            existing['dialogStyle'] = analysis.get('dialogStyle', {})
        else:
            # 合并对话风格（取较新的）
            existing['dialogStyle'].update(analysis.get('dialogStyle', {}))

        # 追加共同回忆（去重）
        existing_memories = existing.get('sharedMemories', [])
        existing_ids = {m.get('id') for m in existing_memories}
        for mem in analysis.get('sharedMemories', []):
            if mem['id'] not in existing_ids:
                existing_memories.append(mem)
        existing['sharedMemories'] = existing_memories

        # 合并昵称
        if 'nicknames' not in existing:
            existing['nicknames'] = analysis.get('nicknames', {})
        else:
            for key in ['companionCallsUser', 'userCallsCompanion', 'detectedPatterns']:
                existing_list = existing['nicknames'].get(key, [])
                new_list = analysis.get('nicknames', {}).get(key, [])
                existing_ids_set = {json.dumps(e, sort_keys=True) for e in existing_list}
                for item in new_list:
                    if json.dumps(item, sort_keys=True) not in existing_ids_set:
                        existing_list.append(item)
                existing['nicknames'][key] = existing_list

        # 合并情感画像
        existing['emotionalProfile'] = analysis.get('emotionalProfile', {})

        # 追加高频话题
        existing['frequentTopics'] = analysis.get('frequentTopics', [])

        # 互动模式
        existing['interactionPatterns'] = analysis.get('interactionPatterns', {})

        # 更新时间
        existing['updatedAt'] = datetime.now().isoformat()

        with open(self.analysis_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _update_relationship_data(self, analysis: Dict) -> None:
        """将分析结果中的关键信息同步到 relationship.json"""
        rel_file = self.data_dir / "relationship.json"
        if not rel_file.exists():
            return

        try:
            with open(rel_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        active_id = data.get('activeCompanionId')
        if not active_id or active_id not in data.get('companions', {}):
            return

        companion = data['companions'][active_id]

        # 同步共同回忆
        memories = companion.get('relationship', {}).get('sharedMemories', [])
        existing_ids = {m.get('id') for m in memories}
        for mem in analysis.get('sharedMemories', []):
            if mem['id'] not in existing_ids:
                memories.append(mem)
        companion.setdefault('relationship', {})['sharedMemories'] = memories

        # 同步昵称
        nicknames = analysis.get('nicknames', {})
        comp_calls = nicknames.get('companionCallsUser', [])
        user_calls = nicknames.get('userCallsCompanion', [])

        if comp_calls:
            companion.setdefault('agent', {}).setdefault('nicknames', [])
            for call in comp_calls:
                if call['term'] not in companion['agent']['nicknames']:
                    companion['agent']['nicknames'].append(call['term'])

        if user_calls:
            companion.setdefault('user', {}).setdefault('preferences', {}).setdefault('nicknames', [])
            for call in user_calls:
                if call['term'] not in companion['user']['preferences']['nicknames']:
                    companion['user']['preferences']['nicknames'].append(call['term'])

        # 同步情感风格到陪伴者性格
        emotional_profile = analysis.get('emotionalProfile', {})
        comp_style = emotional_profile.get('companionEmotionalStyle', '')
        if comp_style:
            personality = companion.get('agent', {}).get('personality', '')
            if comp_style not in personality:
                companion['agent']['personality'] = f"{personality}，{comp_style}" if personality else comp_style

        # 同步对话风格
        dialog_style = analysis.get('dialogStyle', {})
        comp_vibes = dialog_style.get('companion', {}).get('vibeTags', [])
        if comp_vibes:
            personality = companion.get('agent', {}).get('personality', '')
            vibe_str = '、'.join(comp_vibes)
            if vibe_str not in personality:
                companion['agent']['personality'] = f"{personality}，{vibe_str}" if personality else vibe_str

        data['updatedAt'] = datetime.now().isoformat()

        with open(rel_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_analysis(self) -> Dict:
        """获取当前分析结果"""
        if self.analysis_file.exists():
            try:
                with open(self.analysis_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def list_imports(self) -> List[Dict]:
        """列出所有导入记录"""
        data = self.get_analysis()
        return data.get('imports', [])


# ========== CLI 入口 ==========
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='聊天记录导入与分析工具')
    parser.add_argument('file', help='聊天记录文件路径')
    parser.add_argument('--source', default='auto', choices=['auto', 'wechat', 'qq', 'generic'],
                        help='聊天来源 (默认自动检测)')
    parser.add_argument('--companion', default='', help='陪伴者名字')
    parser.add_argument('--user', default='', help='用户名字')
    parser.add_argument('--start-date', default=None, help='起始日期 YYYY-MM-DD')
    parser.add_argument('--end-date', default=None, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--keywords', nargs='*', default=None, help='关键词过滤')
    parser.add_argument('--exclude', nargs='*', default=None, help='排除关键词')
    parser.add_argument('--senders', nargs='*', default=None, help='发送者过滤')
    parser.add_argument('--no-sensitive', action='store_true', help='禁用自动敏感内容脱敏')
    parser.add_argument('--data-dir', default=None, help='数据目录路径')

    args = parser.parse_args()

    data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), '..', 'references')
    importer = ChatImporter(data_dir)

    result = importer.import_chat(
        file_path=args.file,
        source=args.source,
        companion_name=args.companion,
        user_name=args.user,
        start_date=args.start_date,
        end_date=args.end_date,
        keywords=args.keywords,
        exclude_keywords=args.exclude,
        senders=args.senders,
        disable_auto_sensitive=args.no_sensitive,
    )

    print(f"\n{'='*50}")
    print(f"导入结果: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"文件格式: {result['format']}")
    print(f"原始消息: {result['totalRaw']} 条")
    print(f"过滤后: {result['totalFiltered']} 条")
    print(f"状态: {result['message']}")

    if result['success'] and result.get('analysis'):
        analysis = result['analysis']
        print(f"\n--- 分析摘要 ---")
        print(analysis.get('summary', '无'))
