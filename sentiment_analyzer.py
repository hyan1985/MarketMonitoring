import json
import re
import os
from datetime import datetime

from beijing_time import format_beijing, now_beijing_naive, today_beijing
import jieba
from collections import Counter
import sys

class SentimentAnalyzer:
    def __init__(self, config_path="/Users/hyan/Desktop/词频情绪/config.json"):
        self.config_path = config_path
        self.bullish_words = []
        self.bearish_words = []
        self.bullish_phrases = []
        self.bearish_phrases = []
        self.bearish_regex = []
        self.neutral_patterns = []
        self.negation_words = []
        self.spam_keywords = []
        self.half_life_hours = 12.0
        self.load_config()
        self.init_jieba()

    def load_config(self):
        """Load lexicon and parameters from config.json"""
        if not os.path.exists(self.config_path):
            print(f"  [Analyzer] Error: Config file not found at {self.config_path}", file=sys.stderr)
            # Fallback to defaults
            self.bullish_words = ["抄底", "起飞", "翻倍", "涨停", "必涨", "锁仓", "加仓", "满仓", "冲", "大利好", "低估", "金叉", "主升浪", "起飞前夜", "筹码集中"]
            self.bearish_words = ["割肉", "销户", "暴跌", "垃圾", "退市", "跑路", "踩雷", "完蛋", "亏麻", "清仓", "烂票", "出货", "崩盘", "被套"]
            self.bullish_phrases = []
            self.bearish_phrases = []
            self.bearish_regex = []
            self.neutral_patterns = []
            self.negation_words = ["不", "不要", "没", "没有", "别", "无法", "未", "绝不", "不能", "并非"]
            self.spam_keywords = ["广告", "配资", "港股通", "资金流入", "资金流出", "大宗交易", "融资融券"]
            self.half_life_hours = 12.0
            return
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.bullish_words = config.get("bullish_words", [])
                self.bearish_words = config.get("bearish_words", [])
                self.bullish_phrases = config.get("bullish_phrases", [])
                self.bearish_phrases = config.get("bearish_phrases", [])
                self.bearish_regex = config.get("bearish_regex", [])
                self.neutral_patterns = config.get("neutral_patterns", [])
                self.negation_words = config.get("negation_words", ["不", "不要", "没", "没有", "别", "无法", "未", "绝不", "不能", "并非"])
                self.spam_keywords = config.get("spam_keywords", ["广告", "配资", "港股通", "资金流入", "资金流出", "大宗交易", "融资融券"])
                self.half_life_hours = config.get("time_decay_half_life_hours", 12.0)
            print(
                f"  [Analyzer] Lexicon: {len(self.bullish_words)} bull / {len(self.bearish_words)} bear words, "
                f"{len(self.bullish_phrases)} bull / {len(self.bearish_phrases)} bear phrases, "
                f"{len(self.bearish_regex)} bear regex, {len(self.neutral_patterns)} news-neutral patterns."
            )
            print(f"  [Analyzer] Advanced filter: {len(self.negation_words)} negation, {len(self.spam_keywords)} spam, decay {self.half_life_hours}h.")
        except Exception as e:
            print(f"  [Analyzer] Error reading config: {e}", file=sys.stderr)

    def init_jieba(self):
        """Initialize jieba word segmentation, adding custom keywords to ensure correct segmentation"""
        print("  [Analyzer] Initializing jieba word segmenter...")
        # Add sentiment keywords to jieba dictionary to prevent them from being split
        for w in self.bullish_words + self.bearish_words + self.bullish_phrases + self.bearish_phrases:
            jieba.add_word(w)
        # Warmup jieba
        list(jieba.cut("A股主升浪起飞前夜，满仓抄底冲！"))
        print("  [Analyzer] jieba initialized successfully.")

    def parse_datetime(self, time_str, reference_date=None):
        """Standardize Guba's date format (e.g. '05-17 08:55' or '08:55') into standard datetime pieces"""
        time_str = time_str.strip()
        ref = reference_date or today_beijing()
        current_year = ref.year
        current_date_str = ref.strftime("%Y-%m-%d")
        
        date_part = current_date_str
        hour_part = "00:00"
        
        if '-' in time_str: # e.g. "05-17 08:55"
            match = re.search(r'(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', time_str)
            if match:
                month, day, hr, mn = match.groups()
                date_part = f"{current_year}-{month}-{day}"
                hour_part = f"{hr}:{mn}"
            else:
                match_day = re.search(r'(\d{2})-(\d{2})', time_str)
                if match_day:
                    month, day = match_day.groups()
                    date_part = f"{current_year}-{month}-{day}"
        elif ':' in time_str: # e.g. "08:55" (meaning today)
            date_part = current_date_str
            match_time = re.search(r'(\d{2}):(\d{2})', time_str)
            if match_time:
                hour_part = f"{match_time.group(1)}:{match_time.group(2)}"
        
        return date_part, hour_part

    def _is_news_neutral(self, text):
        """True when text looks like overseas/index headline, not retail sentiment."""
        for pattern in self.neutral_patterns:
            if re.search(pattern, text):
                return True
        return False

    def _match_phrases_and_regex(self, text, matched_bullish, matched_bearish):
        """Substring phrases and contextual regex (e.g. flee to Nikkei/Nasdaq)."""
        for phrase in self.bullish_phrases:
            if phrase in text:
                matched_bullish.append(phrase)

        for phrase in self.bearish_phrases:
            if phrase in text:
                matched_bearish.append(phrase)

        is_news = self._is_news_neutral(text)
        for rule in self.bearish_regex:
            pattern = rule.get("pattern", "")
            tag = rule.get("tag", "bear_regex")
            if not pattern:
                continue
            if rule.get("skip_if_news") and is_news:
                continue
            if re.search(pattern, text):
                matched_bearish.append(tag)

    # 反讽前置线索（出现在多头词前面）
    _SARCASM_PREFIX_CUES = (
        "所谓的", "所谓", "你们说的", "你以为的", "什么破", "什么",
        "哪来的", "哪有", "吹的", "假的", "假", "呵呵", "你们吹的",
        "又是你们", "好一个", "真会", "真棒", "厉害",
    )
    # 反讽后置线索（出现在多头词后面）
    _SARCASM_SUFFIX_CUES = (
        "呢", "啊这是", "个屁", "你个头", "罢了", "？呵呵", "?呵呵",
        "是吧", "吗", "哦",
    )
    # 阴阳对比：多头词附近出现惨淡结果
    _SARCASM_BAD_OUTCOMES = (
        "半山腰", "地板", "地心", "腰斩", "跌停", "创新低", "割肉",
        "血洗", "深套", "爆仓", "跌麻", "亏麻", "一天跌", "又跌",
        "跌三个", "跌停潮", "姥姥家", "地心里",
    )
    # 整句阴阳标记：出现则把句内多头词整体翻空
    _SARCASM_SENTENCE_MARKERS = (
        "呵呵", "个屁", "你个头", "真会玩", "牛到姥姥家", "飞到地心",
        "香到割肉", "快乐你们不懂", "氛围拉满", "又创新低", "抄到半山腰",
        "买在半山腰", "干到腰斩",
    )

    def _has_sarcasm_cue(self, text, keyword):
        """True when keyword sits in sarcasm prefix/suffix context."""
        if not text or not keyword:
            return False
        start = 0
        while True:
            pos = text.find(keyword, start)
            if pos < 0:
                break
            prefix = text[max(0, pos - 14) : pos]
            suffix = text[pos + len(keyword) : pos + len(keyword) + 8]
            if any(cue in prefix for cue in self._SARCASM_PREFIX_CUES):
                return True
            if any(cue in suffix for cue in self._SARCASM_SUFFIX_CUES):
                # 「牛市吗/牛市呢/起飞了是吧」偏反问/阴阳；避免「牛市来了」被误伤
                if any(cue in suffix for cue in ("呢", "啊这是", "个屁", "你个头", "罢了", "？呵呵", "?呵呵", "是吧")):
                    return True
                # 「吗」单独太宽，需再配问号或嘲讽词
                if "吗" in suffix and ("？" in text or "?" in text or "呵呵" in text or "又是" in prefix):
                    return True
            start = pos + 1
        return False

    def _has_contrast_irony(self, text):
        """多头用语 + 惨淡结果同句，典型阴阳对比。"""
        if not text:
            return False
        bull_hits = [w for w in self.bullish_words if w in text]
        bull_hits += [p for p in self.bullish_phrases if p in text]
        # 慢牛/长线/价值投资 常被阴阳，但不在 bullish_words 里
        soft_bull = ("慢牛", "长线", "价值投资", "黄金买点", "牛市氛围")
        bull_hits += [w for w in soft_bull if w in text]
        if not bull_hits:
            return False
        if any(bad in text for bad in self._SARCASM_BAD_OUTCOMES):
            return True
        # 「真是太牛了/厉害厉害」+ 下跌语境
        if re.search(r"(?:真是|真的|太)?(?:太)?(?:牛了|厉害|真棒|可以的)", text) and re.search(
            r"(?:跌|创新低|腰斩|跌停|割肉|亏)", text
        ):
            return True
        return False

    def _sentence_sarcasm(self, text):
        """整句阴阳标记。"""
        if not text:
            return False
        if any(m in text for m in self._SARCASM_SENTENCE_MARKERS):
            return True
        if re.search(r"(?:牛市|慢牛|起飞|抄底|主升浪?).{0,4}[？?].{0,6}(?:屁|呵呵|呢)", text):
            return True
        if re.search(r"(?:抄|涨|飞).{0,2}你个头", text):
            return True
        # 「又是主升浪，天天主升浪」复读阴阳
        if re.search(r"又是.{0,6}(?:主升浪?|抄底|牛市|起飞|满仓).{0,12}天天", text):
            return True
        if re.search(r"天天.{0,4}(?:主升浪?|抄底|牛市|起飞)", text) and "又是" in text:
            return True
        return False

    def analyze_single_text(self, text):
        """Analyze a single piece of text and return sentiment score and matched words with negation flipping"""
        if not text:
            return 0.0, [], []
        
        matched_bullish = []
        matched_bearish = []
        self._match_phrases_and_regex(text, matched_bullish, matched_bearish)

        sentence_sarcasm = self._sentence_sarcasm(text) or self._has_contrast_irony(text)

        # Segment text for lexicon tokens
        words = jieba.lcut(text)
        
        for i, word in enumerate(words):
            is_bullish = word in self.bullish_words
            is_bearish = word in self.bearish_words
            
            if is_bullish or is_bearish:
                # Check negation in preceding 2 words
                has_negation = False
                for lookback in [1, 2]:
                    if i - lookback >= 0:
                        prev_w = words[i - lookback]
                        if prev_w in self.negation_words:
                            has_negation = True
                            break

                # 反讽/阴阳：多头词翻空
                has_sarcasm = is_bullish and (
                    self._has_sarcasm_cue(text, word) or sentence_sarcasm
                )
                
                if has_negation or has_sarcasm:
                    if is_bullish:
                        tag = f"讽-{word}" if has_sarcasm and not has_negation else f"不-{word}"
                        matched_bearish.append(tag)
                    else:
                        matched_bullish.append(f"不-{word}")
                else:
                    if is_bullish:
                        matched_bullish.append(word)
                    else:
                        matched_bearish.append(word)

        # 对比阴阳命中但词库未命中多头词时，补一条空头标记，避免漏判
        if sentence_sarcasm and not matched_bearish and not matched_bullish:
            matched_bearish.append("阴阳语气")
        elif sentence_sarcasm and matched_bullish:
            # 把残留多头短语也翻空（短语匹配阶段未翻转）
            flipped = []
            keep_bull = []
            for w in matched_bullish:
                if w in self.bullish_phrases or w in self.bullish_words:
                    flipped.append(f"讽-{w}")
                else:
                    keep_bull.append(w)
            matched_bullish = keep_bull
            matched_bearish.extend(flipped)
        
        pos = len(matched_bullish)
        neg = len(matched_bearish)
        total = pos + neg
        
        score = 0.0
        if total > 0:
            score = (pos - neg) / total
            
        return score, matched_bullish, matched_bearish

    def analyze_posts(self, posts, reference_time=None):
        """Process a list of posts, filter spams, apply advanced weighting, and perform aggregation"""
        print(f"[Analyzer] Scoring {len(posts)} posts...")
        analyzed_posts = []
        
        bullish_counter = Counter()
        bearish_counter = Counter()
        
        author_counts = {}
        spam_skipped_count = 0
        now = reference_time or now_beijing_naive()
        reference_date = now.date()
        
        for post in posts:
            title = post.get("title", "")
            author = post.get("author", "匿名")
            
            # 1. AD/Robot Spam Filtering
            is_spam = False
            for kw in self.spam_keywords:
                if kw in title:
                    is_spam = True
                    break
            
            if is_spam:
                spam_skipped_count += 1
                continue
                
            # 2. Score text with negation flipping
            score, pos_words, neg_words = self.analyze_single_text(title)
            
            # Record word matches for stats
            bullish_counter.update(pos_words)
            bearish_counter.update(neg_words)
            
            date_part, hour_part = self.parse_datetime(
                post.get("time", ""), reference_date=reference_date
            )
            hour_bucket = hour_part.split(":")[0] + ":00" # group by hour, e.g. "08:00"
            
            # 3. Spammer/Multi-post Weight Penalty
            author_counts[author] = author_counts.get(author, 0) + 1
            spammer_penalty = 0.5 ** (author_counts[author] - 1)
            
            # 4. Time Decay Factor
            try:
                post_dt = datetime.strptime(f"{date_part} {hour_part}", "%Y-%m-%d %H:%M")
                delta = now - post_dt
                delta_hours = max(0.0, delta.total_seconds() / 3600.0)
            except Exception:
                delta_hours = 0.0
                
            time_decay = 0.5 ** (delta_hours / self.half_life_hours)
            
            # 5. Calculate final weights
            read_count = post.get("read_count", 0)
            raw_weight = read_count + 1
            final_weight = raw_weight * spammer_penalty * time_decay
            
            analyzed_posts.append({
                "post_id": post.get("post_id", ""),
                "title": title,
                "read_count": read_count,
                "reply_count": post.get("reply_count", 0),
                "author": author,
                "time": post.get("time", ""),
                "date": date_part,
                "hour": hour_bucket,
                "href": post.get("href", ""),
                "source": post.get("source", "eastmoney"),
                "sentiment_score": score,
                "pos_words": pos_words,
                "neg_words": neg_words,
                "spammer_penalty": round(spammer_penalty, 4),
                "time_decay": round(time_decay, 4),
                "final_weight": round(final_weight, 4)
            })

        print(f"  [Analyzer] Advanced filter results: skipped {spam_skipped_count} spam/robot posts.")

        # --- Aggregate calculations ---
        # 1. Overall Weighted Sentiment Score
        total_weight = 0.0
        weighted_score_sum = 0.0
        
        pos_posts_count = 0
        neg_posts_count = 0
        neu_posts_count = 0
        
        for p in analyzed_posts:
            weight = p["final_weight"]
            total_weight += weight
            weighted_score_sum += p["sentiment_score"] * weight
            
            if p["sentiment_score"] > 0:
                pos_posts_count += 1
            elif p["sentiment_score"] < 0:
                neg_posts_count += 1
            else:
                neu_posts_count += 1
                
        overall_weighted_score = (weighted_score_sum / total_weight) if total_weight > 0 else 0.0
        
        # 2. Daily Weighted Sentiment Score
        daily_groups = {}
        for p in analyzed_posts:
            d = p["date"]
            if d not in daily_groups:
                daily_groups[d] = {"weighted_sum": 0.0, "total_weight": 0.0, "count": 0}
            w = p["final_weight"]
            daily_groups[d]["weighted_sum"] += p["sentiment_score"] * w
            daily_groups[d]["total_weight"] += w
            daily_groups[d]["count"] += 1
            
        daily_trends = []
        for d, vals in sorted(daily_groups.items()):
            daily_trends.append({
                "date": d,
                "sentiment_score": round(vals["weighted_sum"] / vals["total_weight"], 4) if vals["total_weight"] > 0 else 0.0,
                "count": vals["count"]
            })
            
        # 3. Hourly Weighted Sentiment Score (helpful if posts span mainly one/two days)
        # Combine date + hour for a unique hourly key, e.g. "2026-05-17 08:00"
        hourly_groups = {}
        for p in analyzed_posts:
            h_key = f"{p['date']} {p['hour']}"
            if h_key not in hourly_groups:
                hourly_groups[h_key] = {"weighted_sum": 0.0, "total_weight": 0.0, "count": 0}
            w = p["final_weight"]
            hourly_groups[h_key]["weighted_sum"] += p["sentiment_score"] * w
            hourly_groups[h_key]["total_weight"] += w
            hourly_groups[h_key]["count"] += 1
            
        hourly_trends = []
        for h_key, vals in sorted(hourly_groups.items()):
            hourly_trends.append({
                "time": h_key,
                "sentiment_score": round(vals["weighted_sum"] / vals["total_weight"], 4) if vals["total_weight"] > 0 else 0.0,
                "count": vals["count"]
            })

        # Sort hourly trends chronologically
        hourly_trends.sort(key=lambda x: x["time"])

        # Construct final output dictionary
        sentiment_data = {
            "summary": {
                "overall_weighted_score": round(overall_weighted_score, 4),
                "total_posts": len(analyzed_posts) + spam_skipped_count,
                "valid_posts": len(analyzed_posts),
                "spam_posts": spam_skipped_count,
                "bullish_posts": pos_posts_count,
                "bearish_posts": neg_posts_count,
                "neutral_posts": neu_posts_count,
                "last_updated": format_beijing(),
                "sources_used": sorted({p.get("source", "eastmoney") for p in analyzed_posts}),
            },
            "top_bullish_words": [{"word": k, "count": v} for k, v in bullish_counter.most_common(15)],
            "top_bearish_words": [{"word": k, "count": v} for k, v in bearish_counter.most_common(15)],
            "daily_trends": daily_trends,
            "hourly_trends": hourly_trends,
            "posts": analyzed_posts
        }
        
        return sentiment_data

    def save_results(self, data, output_path="/Users/hyan/Desktop/词频情绪/data.json"):
        """Save summary/trends to data.json; posts go to compact posts.json."""
        from data_store import save_bundle

        try:
            existing_daily = {}
            existing_hourly = {}

            if os.path.exists(output_path):
                try:
                    from data_store import load_bundle

                    old_data = load_bundle(output_path, include_posts=False)
                    for item in old_data.get("daily_trends", []):
                        if "date" in item:
                            existing_daily[item["date"]] = item
                    for item in old_data.get("hourly_trends", []):
                        if "time" in item:
                            existing_hourly[item["time"]] = item
                except Exception as ex:
                    print(f"[Analyzer] Warning reading existing database for merging: {ex}")

            new_daily = {item["date"]: item for item in data.get("daily_trends", []) if "date" in item}
            for d, item in existing_daily.items():
                if d not in new_daily:
                    new_daily[d] = item

            new_hourly = {item["time"]: item for item in data.get("hourly_trends", []) if "time" in item}
            for t, item in existing_hourly.items():
                if t not in new_hourly:
                    new_hourly[t] = item

            data["daily_trends"] = [new_daily[d] for d in sorted(new_daily.keys())]
            # Cap hourly history to reduce unbounded growth (~30 days of buckets)
            sorted_hourly = [new_hourly[t] for t in sorted(new_hourly.keys())]
            data["hourly_trends"] = sorted_hourly[-720:]

            save_bundle(data, output_path)
            print(f"[Analyzer] Saved dashboard bundle to {output_path} (+ posts.json)")
        except Exception as e:
            print(f"[Analyzer] Error saving results: {e}", file=sys.stderr)

if __name__ == "__main__":
    # Test data
    sample_posts = [
        {"post_id": "1", "title": "A股起飞前夜，满仓抄底冲冲冲！", "read_count": 1000, "reply_count": 10, "author": "牛散", "time": "05-17 10:15"},
        {"post_id": "2", "title": "亏麻了，这垃圾股，抓紧割肉销户跑路！", "read_count": 5000, "reply_count": 50, "author": "韭菜", "time": "05-17 11:20"}
    ]
    analyzer = SentimentAnalyzer()
    res = analyzer.analyze_posts(sample_posts)
    print(json.dumps(res["summary"], indent=2))
