"""
风险舆情自动分级器 | Risk Sentiment Auto-Classifier
=====================================================
设计目标：替代 index.html 中手工维护的 level / highRelevance，根据事件特征自动判定。

三维打分模型
------------
  D1 事件类型基线分 —— 事件本身对还款能力的威胁程度
  D2 主体角色系数 —— 借款人 vs 保证人的影响差异
  D3 量化调节因子 —— 金额、频次、时间衰减

最终分级规则
------------
  score = D1 x D2 + D3  ->  映射到 严重/较重/关注
  highRelevance 由 D2 主体角色 + 事件是否直接指向核心偿付能力决定

使用方式
--------
  from risk_classifier import classify_event, classify_batch, parse_llm_output
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

_event_base = {
    "失信被执行": 100, "债务违约": 100, "兑付困难": 100,
    "破产": 100, "清算": 100, "破产重整": 98,
    "新增被执行": 92, "重大被执行": 92,
    "限制高消费": 85, "资产冻结": 82, "查封": 80,
    "评级下调": 78, "担保代偿": 78,
    "重大诉讼": 75, "仲裁": 73, "担保履约恶化": 72,
    "展期": 65, "评级关注": 60, "重大行政处罚": 58,
    "监管处罚": 55, "行政处罚": 50, "工程款争议": 55,
    "环保处罚": 48, "信息披露违规": 45,
    "区域融资压力": 40, "经营异常": 45,
}
EVENT_TYPE_BASE = _event_base

_KEYWORD_PATTERNS = [
    ("失信|失信被执行|失信名单|失信记录", "失信被执行"),
    ("被执行|执行信息|执行公开|新增执行", "新增被执行"),
    ("限制高消费|限高|限制消费", "限制高消费"),
    ("债务违约|债券违约|本息违约|实质性违约", "债务违约"),
    ("兑付困难|兑付危机|兑付风险|到期未兑付", "兑付困难"),
    ("破产重整|破产清算|破产申请|宣告破产", "破产重整"),
    ("资产冻结|账户冻结|股权冻结|资金冻结", "资产冻结"),
    ("查封|财产查封", "查封"),
    ("评级下调|信用下调|展望负面|降级", "评级下调"),
    ("评级关注|列入观察|评级展望调整", "评级关注"),
    ("展期|延期兑付|延期偿还", "展期"),
    ("重大诉讼|诉讼进展|诉讼公告", "重大诉讼"),
    ("仲裁|商事仲裁", "仲裁"),
    ("行政处罚|行政罚款|责令改正|监管函", "行政处罚"),
    ("信息披露违规|信披违规|未及时披露", "信息披露违规"),
    ("担保代偿|担保履约|代偿义务", "担保代偿"),
    ("工程款|支付争议|合同纠纷", "工程款争议"),
    ("融资压力|再融资困难|融资环境", "区域融资压力"),
    ("经营异常|停产|停工|重大亏损", "经营异常"),
    ("清算|解散|注销", "清算"),
]

KEYWORD_TO_TYPE = [(re.compile(p), t) for p, t in _KEYWORD_PATTERNS]


def infer_event_type(text):
    best_type, best_len = "其他", 0
    for pattern, event_type in KEYWORD_TO_TYPE:
        m = pattern.search(text)
        if m and len(m.group()) > best_len:
            best_type, best_len = event_type, len(m.group())
    return best_type


ROLE_MULTIPLIER = {
    "借款人": 1.0, "共同借款人": 1.0,
    "保证人": 1.0, "担保人": 1.0,
    "关联方": 1.0, "未知": 1.0,
}

_HIGH_RELEVANCE_TYPES = {
    "失信被执行", "债务违约", "破产", "清算", "破产重整",
    "担保代偿", "担保履约恶化", "评级下调",
}

AMOUNT_ADJUST = {"特大": 8, "大额": 4, "中额": 0, "小额": -4, "未知": 0}
FREQUENCY_ADJUST = {"持续": 6, "多次": 3, "首次": 0, "未知": 0}


def time_adjust(days_ago):
    if days_ago <= 7:
        return 0.0
    if days_ago <= 30:
        return -(days_ago - 7) * 0.4
    return -10.0


def score_to_level(score):
    if score >= 82:
        return "严重"
    if score >= 60:
        return "较重"
    return "关注"


def determine_high_relevance(event_type, role, score):
    """严重和较重的事件均视为高相关，直接关联还款能力。"""
    if score >= 82:
        return True
    if score >= 60:
        return True
    return False


@dataclass
class RiskEvent:
    entity_name: str
    role: str
    title: str = ""
    summary: str = ""
    content: str = ""
    event_type: str = ""
    amount_hint: str = "未知"
    frequency: str = "未知"
    days_ago: int = 7
    sources: list = field(default_factory=list)

    def combined_text(self):
        return " ".join(filter(None, [self.title, self.summary, self.content]))


@dataclass
class RiskResult:
    level: str
    high_relevance: bool
    score: float
    event_type: str
    event_type_base: int
    role_multiplier: float
    quant_adjust: float
    rationale: str

    def to_dict(self):
        return {
            "level": self.level,
            "highRelevance": self.high_relevance,
            "score": self.score,
            "eventType": self.event_type,
            "rationale": self.rationale,
        }


def classify_event(event):
    event_type = event.event_type or infer_event_type(event.combined_text())
    type_base = EVENT_TYPE_BASE.get(event_type, 30)
    role_mul = ROLE_MULTIPLIER.get(event.role, 0.60)
    quant_adj = 0.0
    quant_adj += AMOUNT_ADJUST.get(event.amount_hint, 0.0)
    quant_adj += FREQUENCY_ADJUST.get(event.frequency, 0.0)
    quant_adj += time_adjust(event.days_ago)
    score = type_base * role_mul + quant_adj
    score = max(0.0, min(100.0, score))
    level = score_to_level(score)
    high_rel = determine_high_relevance(event_type, event.role, score)
    parts = [f"事件类型={event_type}({type_base})"]
    if event.role in ROLE_MULTIPLIER:
        parts.append(f"角色系数={role_mul:.2f}")
    if quant_adj != 0:
        parts.append(f"调节={quant_adj:+.1f}")
    parts.append(f"总分={score:.0f}")
    return RiskResult(level=level, high_relevance=high_rel, score=round(score, 1),
                      event_type=event_type, event_type_base=type_base,
                      role_multiplier=role_mul, quant_adjust=round(quant_adj, 1),
                      rationale="，".join(parts))


def classify_batch(events):
    return [classify_event(e) for e in events]


# LLM 输出解析器
_SPLIT_RE = re.compile(r"\n(?=(?:\d+[.、)]|事件\s*[一二三四五六七八九十\d]+[.、:]))")

_KNOWN_SOURCES = [
    "中国执行信息公开网", "中国裁判文书网", "信用中国", "Choice",
    "iFinD", "Wind", "企查查", "天眼查", "东方财富",
]


def parse_llm_output(raw_text, entity_name, role):
    events = []
    if re.search(r"未发现|未检索到|不存在.*重大.*负面|无重大.*舆情", raw_text):
        return events
    blocks = _SPLIT_RE.split(raw_text)
    if len(blocks) <= 1:
        blocks = [raw_text]
    for block in blocks:
        block = block.strip()
        if not block or len(block) < 20:
            continue
        title = ""
        title_match = re.search(r"[《「](.+?)[》」]", block)
        if title_match:
            title = title_match.group(1)
        else:
            lines = block.split("\n")
            title = lines[0].lstrip("0123456789.、) ").strip()[:120]
        days_ago = 7
        date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", block)
        if date_match:
            try:
                event_date = date.fromisoformat(date_match.group(1))
                days_ago = max(0, (date.today() - event_date).days)
            except ValueError:
                pass
        sources = [s for s in _KNOWN_SOURCES if s in block]
        summary = block[:300].replace("\n", " ")
        event_type = infer_event_type(block)
        events.append(RiskEvent(
            entity_name=entity_name, role=role, title=title,
            summary=summary, content=block, event_type=event_type,
            days_ago=days_ago, sources=sources,
        ))
    return events


if __name__ == "__main__":
    tests = [
        RiskEvent(entity_name="杭州东部城建", role="借款人",
                  event_type="新增被执行", amount_hint="大额", days_ago=1, frequency="首次"),
        RiskEvent(entity_name="嵊州交投", role="保证人",
                  event_type="评级关注", amount_hint="未知", days_ago=3, frequency="首次"),
        RiskEvent(entity_name="诸暨国资", role="借款人",
                  event_type="重大诉讼", amount_hint="未知", days_ago=5, frequency="首次"),
        RiskEvent(entity_name="桐庐国资", role="借款人",
                  event_type="行政处罚", amount_hint="未知", days_ago=7, frequency="首次"),
        RiskEvent(entity_name="某城投A", role="保证人",
                  event_type="失信被执行", amount_hint="大额", days_ago=2, frequency="首次"),
        RiskEvent(entity_name="某城投B", role="借款人",
                  event_type="债务违约", amount_hint="特大", days_ago=0, frequency="多次"),
        RiskEvent(entity_name="某城投C", role="保证人",
                  event_type="评级关注", amount_hint="未知", days_ago=3, frequency="首次"),
        RiskEvent(entity_name="某城投E", role="保证人",
                  event_type="资产冻结", amount_hint="大额", days_ago=1, frequency="首次"),
        RiskEvent(entity_name="某城投D", role="借款人",
                  event_type="限制高消费", amount_hint="中额", days_ago=15, frequency="多次"),
    ]
    print("=" * 85)
    print(f"{'主体':<10} {'角色':<6} {'事件类型':<12} {'总分':<6} {'等级':<6} {'高相关':<6} {'工作台':<6} 判定依据")
    print("-" * 85)
    for ev in tests:
        r = classify_event(ev)
        wb = "是" if r.level in ("严重", "较重") else "否"
        print(f"{ev.entity_name:<10} {ev.role:<6} {r.event_type:<12} {r.score:<6.0f} {r.level:<6} {'是' if r.high_relevance else '否':<6} {wb:<6} {r.rationale}")
    print("=" * 85)
    sev = sum(1 for e in tests if classify_event(e).level == "严重")
    hi = sum(1 for e in tests if classify_event(e).level == "较重")
    wa = sum(1 for e in tests if classify_event(e).level == "关注")
    print(f"\n统计：严重 {sev} | 较重 {hi} | 关注 {wa}")