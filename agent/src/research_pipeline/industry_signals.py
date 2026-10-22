# -*- coding: utf-8 -*-
"""产业信号资产（VR chokepoint_keywords / industry_tags 移植，python 常量）。

CHOKEPOINT_RULES：八类卡口的确定性关键词筛子。判定规则（与 VR 一致）：
① 标题先按 ;；,，。 拆子句，keywords / negatives 在**同一子句**内判定
   （「签订订单；未涨价」这样的并列事项不互相否决）；
② `re:` 前缀是正则（中文需要上下文约束时用，如「签订」必须跟销售/供货）；
③ 纯 ASCII 关键词按词边界匹配，中文按子串；
④ negatives 命中则该子句的该类别不算。

classify_announcement / industry_temperature 只做字符串匹配：不调模型、
不联网、无随机性，同输入永远同输出——分类结果可以直接进证据链被审计。

INDUSTRY_TEMPERATURE：行业温度标签表（强=供给紧、弱=供给松）。温度是
**行业层面的定性旁证**，不是本公司数据，两向词互抵时不给温度。
"""

from __future__ import annotations

import re

DECISION_HINTS: dict[str, str] = {
    "涨价": "涨价函=供给紧的直接证据；看涨幅是否传导到毛利率（下季财报裁决）",
    "扩产": "扩产=管理层对需求的判断；跟踪投产时点与爬坡良率",
    "减产停产": "上游减产=供给刚性变量；本公司停产=直接业绩风险",
    "订单合同": "订单=兑现路径；看金额占营收比与交付期",
    "认证导入": "送样≠订单；认证通过才算导入成立（判定从严）",
    "收购合资": "看标的资产与本公司供给卡口的关系，不看溢价故事",
    "供需": "供给侧信号：sold out / lead time 拉长是预期差识别线索",
    "管制制裁": "只当打折项：没被点名≠不受影响；「被建议列入」≠「已列入」",
}

CHOKEPOINT_RULES: dict[str, dict] = {
    "涨价": {
        "keywords": ["涨价", "提价", "调价函", "价格上调", "上调价格",
                     "price increase", "price hike"],
        "negatives": ["不涨价", "未涨价", "不提价", "降价"],
    },
    "扩产": {
        "keywords": ["扩产", "扩建", "新建产能", "产能扩张",
                     r"re:(项目|产线|工厂|基地).{0,6}投产",
                     r"re:投产.{0,4}(公告|仪式|运行)", "达产", "产能释放",
                     r"re:募投项目.{0,8}(投产|达产|扩产|建设)", "新厂",
                     "capacity expansion", "new plant", "new fab"],
        "negatives": ["终止", "取消", "暂缓", "延期", "中止"],
    },
    "减产停产": {
        "keywords": ["停产", "减产", "断供", "停工", "停摆", "产线关停",
                     "shutdown", "production halt", "suspend production"],
        "negatives": ["恢复生产", "复产", "复工"],
    },
    "订单合同": {
        "keywords": ["中标", "重大合同", "长协", "长期协议",
                     r"re:签订.{0,8}(销售|供货|采购|框架|重大|订单|供应|战略合作)",
                     r"re:(销售|供货|采购|供应).{0,4}(合同|协议|订单)",
                     r"re:(获得|取得|新增|收到).{0,6}订单",
                     "supply agreement", "long-term agreement", "purchase order"],
        "negatives": ["终止合同", "解除合同", "取消订单", "募集资金",
                      "监管协议", "三方协议", "租赁", "培训", "股权激励", "订单式"],
    },
    "认证导入": {
        "keywords": [r"re:(通过|完成|获得|取得).{0,6}(认证|验证|审核)",
                     r"re:(客户|供应商|体系|产品).{0,2}认证", "送样", "批量供货",
                     "进入供应链", "合格供应商", "客户导入", "量产交付",
                     "qualification", "qualified supplier"],
        "negatives": ["未通过", "认证失败", "会计师", "资格认证考试"],
    },
    "收购合资": {
        "keywords": ["收购", "并购", "合资",
                     r"re:增资.{0,4}(扩股|入股|参股|控股|设立)",
                     r"re:(股权|资产)(转让|收购|出售)", "战略投资",
                     "acquisition", "joint venture"],
        "negatives": ["终止收购", "终止合资", "回购", "募集资金"],
    },
    "供需": {
        "keywords": ["供不应求", "缺货", "紧缺", "排产饱满", "产销两旺", "满产",
                     "订单饱满", "sold out", "shortage", "lead time"],
        "negatives": ["供过于求", "过剩", "去库存"],
    },
    "管制制裁": {
        "keywords": ["出口管制", "实体清单", "制裁", "反制", "关税", "禁令",
                     "entity list", "export control", "sanction", "tariff"],
        "negatives": [],
    },
}

INDUSTRY_TEMPERATURE: dict[str, tuple[str, ...]] = {
    "强": ("供不应求", "缺货", "紧缺", "满产", "产销两旺", "订单饱满",
           "排产饱满", "涨价", "提价", "sold out", "shortage", "lead time"),
    "弱": ("供过于求", "过剩", "降价", "去库存", "减产", "停产",
           "价格下调", "清仓"),
}

_CLAUSE_SPLIT = re.compile(r"[;；,，。]")


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _keyword_matches(keyword: str, clause: str) -> bool:
    """单关键词对单子句：re: 正则 / ASCII 词边界 / 中文子串。"""
    if keyword.startswith("re:"):
        try:
            return re.search(keyword[3:], clause) is not None
        except re.error:
            return False
    if _is_ascii(keyword):
        return re.search(rf"\b{re.escape(keyword)}\b", clause,
                         re.IGNORECASE) is not None
    return keyword in clause


def classify_announcement(title: str) -> "list[str]":
    """标题 → 命中的卡口类别清单（按规则表顺序，去重）。

    子句级 negatives：同一子句里出现排除词则该子句的该类别不算；
    其它子句的命中不受影响（并列事项不互相否决）。
    """
    clauses = [c for c in _CLAUSE_SPLIT.split(str(title or "")) if c.strip()]
    hits: list[str] = []
    for category, rule in CHOKEPOINT_RULES.items():
        for clause in clauses:
            hit = any(_keyword_matches(k, clause) for k in rule["keywords"])
            neg = any(_keyword_matches(n, clause) for n in rule.get("negatives", ()))
            if hit and not neg:
                hits.append(category)
                break
    return hits


def industry_temperature(text: str) -> str:
    """文本 → 行业温度「强」「弱」或 ""（两向词互抵/都没命中不给温度）。"""
    blob = str(text or "").lower()
    if not blob.strip():
        return ""

    def _hits(words: tuple[str, ...]) -> int:
        n = 0
        for w in words:
            if _is_ascii(w):
                n += len(re.findall(rf"\b{re.escape(w.lower())}\b", blob))
            else:
                n += blob.count(w)
        return n

    strong, weak = _hits(INDUSTRY_TEMPERATURE["强"]), _hits(INDUSTRY_TEMPERATURE["弱"])
    if strong and not weak:
        return "强"
    if weak and not strong:
        return "弱"
    return ""
