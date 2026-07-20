"""AI 荐策服务：DeepSeek 代理。

安全说明：
- API Key 由桌面端主进程从加密文件 deepseek.key 解密后注入环境变量（DEEPSEEK_API_KEY）后供本服务读取，
  绝不下发到前端，也绝不出现在浏览器可读取的静态资源里，且不以明文形式落盘于用户数据目录。
- 前端通过本地 /api/ai/analyze 调用本服务，由本服务代理转发到 DeepSeek，
  从而避免 CORS 且避免密钥泄露。
"""
from __future__ import annotations

import json
import os

DEFAULT_BASE = "https://api.deepseek.com/v1"


def load_ai_config() -> dict:
    """返回 {api_key, model, base_url}。

    Key 由桌面端主进程从加密文件（deepseek.key）解密后注入环境变量 DEEPSEEK_API_KEY，
    这里只读取该环境变量，绝不读取任何落盘明文 key 文件。
    """
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return {
            "api_key": key,
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE),
        }
    return {}


def has_key() -> bool:
    return bool(load_ai_config().get("api_key"))


def _build_messages(context: dict) -> list[dict]:
    today = context.get("today") or ""
    weekday = context.get("weekday") or ""
    goals = context.get("goals") or []
    recent = context.get("recent") or []
    planned = context.get("planned") or []

    def g(x):
        return x or ""

    goals_txt = "\n".join(
        f"- {g(goal.get('title'))}" + (f"：{g(goal.get('description'))}" if g(goal.get("description")) else "")
        for goal in goals
    ) or "（暂无年度目标）"

    recent_txt = "\n".join(
        f"- [{g(t.get('task_date'))}] {g(t.get('title'))}"
        + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        + (" ✓" if t.get("done") else " ✗")
        for t in recent[-60:]
    ) or "（近 30 天暂无历史）"

    planned_txt = "\n".join(
        f"- {g(t.get('title'))}" + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        for t in planned
    ) or "（今日暂未排程）"

    user = (
        f"今天是 {today}（{weekday}）。\n"
        f"【用户的年度目标 / 长期关注方向】\n{goals_txt}\n\n"
        f"【近 30 天行事历史（日期 / 标题 / 时间 / 完成标记）】\n{recent_txt}\n\n"
        f"【今日已排事件】\n{planned_txt}\n\n"
        f"请基于上述信息，为用户规划今天（{today}）的日程安排。要求：\n"
        "1. 结合年度目标与历史规律，推荐 4~6 条今日宜做之事；\n"
        "2. 每条必须给出开始时间（anchor_time，24 小时制 HH:MM）和预计持续分钟数（duration_min，整数，如 60 代表 1 小时）；无法确定则填 null；\n"
        "3. 每条给出简短中文理由（reason，温暖可爱、有激励感，像一位贴心小谋士在耳边轻语）；\n"
        "4. 不要与「今日已排事件」重复；优先补全用户目标里缺失的具体行动。\n\n"
        "仅输出如下 JSON（不要任何额外文字、不要 markdown 代码块）：\n"
        '{"insight": "一句话洞察","schedule": [{"title": "事项","anchor_time": "HH:MM" 或 null,"duration_min": 60,"reason": "理由"}]}'
    )
    system = (
        "你是「明管家」内置的可爱谋士，语气温暖俏皮、像一位在你身边出谋划策的小伙伴。"
        "善于把用户的长短期目标与作息规律变成具体、可执行的每日安排。必须严格返回 JSON。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def analyze(context: dict) -> dict:
    """调用 DeepSeek，返回 {insight, schedule:[{title,anchor_time,reason}], model}。"""
    cfg = load_ai_config()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("未配置 DeepSeek API Key：请检查内置配置（桌面端 deepseek.key 解密是否成功）。")
    import httpx

    base = cfg.get("base_url") or DEFAULT_BASE
    model = cfg.get("model") or "deepseek-chat"
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": _build_messages(context),
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
                "max_tokens": 1200,
            },
            timeout=60,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            detail = ""
        raise RuntimeError(f"DeepSeek 返回错误 {e.response.status_code}：{detail}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"无法连接 DeepSeek：{e}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except Exception:
        # 模型未严格返回 JSON：原样包裹为单条
        return {
            "insight": "",
            "schedule": [{"title": content[:200], "anchor_time": None, "reason": "（来自 DeepSeek 的自由文本）"}],
            "model": model,
            "raw": True,
        }
    sched = parsed.get("schedule") or []
    out = []
    for it in sched:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        at = it.get("anchor_time") or None
        if isinstance(at, str):
            at = at.strip() or None
        out.append({
            "title": title,
            "anchor_time": at,
            "duration_min": _norm_duration(it.get("duration_min")),
            "reason": str(it.get("reason", "")).strip(),
        })
    return {"insight": str(parsed.get("insight", "")).strip(), "schedule": out, "model": model}


def _norm_duration(v) -> int | None:
    """把 AI 返回的 duration 归一化为整数分钟。"""
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        try:
            n = int(v)
            return n if n > 0 else None
        except ValueError:
            return None
    return None


def _build_plan_messages(context: dict) -> list[dict]:
    plan_text = (context.get("plan_text") or "").strip()
    today = context.get("today") or ""
    weekday = context.get("weekday") or ""
    goals = context.get("goals") or []
    recent = context.get("recent") or []
    planned = context.get("planned") or []

    def g(x):
        return x or ""

    goals_txt = "\n".join(
        f"- {g(goal.get('title'))}" + (f"：{g(goal.get('description'))}" if g(goal.get("description")) else "")
        for goal in goals
    ) or "（暂无年度目标）"

    recent_txt = "\n".join(
        f"- [{g(t.get('task_date'))}] {g(t.get('title'))}"
        + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        + (" ✓" if t.get("done") else " ✗")
        for t in (recent or [])[-40:]
    ) or "（暂无历史）"

    planned_txt = "\n".join(
        f"- {g(t.get('title'))}" + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        for t in planned
    ) or "（今日暂未排程）"

    user = (
        f"今天是 {today}（{weekday}）。\n\n"
        f"【用户的未来计划描述】\n{plan_text or '（未填写）'}\n\n"
        f"【用户的年度目标 / 长期方向】\n{goals_txt}\n\n"
        f"【近 30 天行事历史】\n{recent_txt}\n\n"
        f"【今日已排事件】\n{planned_txt}\n\n"
        "请基于上述「未来计划描述」，为用户将其拆解为具体、可执行的事件安排。要求：\n"
        "1. 把宏大/模糊的计划拆成 4~8 条可落地事项，尽量给出合理的时间段；\n"
        "2. 每条必须给出开始时间（anchor_time，24 小时制 HH:MM）和预计持续分钟数（duration_min，整数，如 60 代表 1 小时）；无法确定则填 null；\n"
        "3. 每条给出简短中文理由（reason，温暖可爱、有激励感，像贴心小谋士在出谋划策），说明它如何服务于该计划；\n"
        "4. 优先补充计划里缺失的支撑行动（学习/准备/复盘等），不要与「今日已排事件」重复。\n\n"
        "仅输出如下 JSON（不要任何额外文字、不要 markdown 代码块）：\n"
        '{"insight": "一句话洞察（点出计划的关键抓手）","schedule": [{"title": "事项","anchor_time": "HH:MM" 或 null,"duration_min": 60,"reason": "理由"}]}'
    )
    system = (
        "你是「明管家」内置的可爱谋士，语气温暖俏皮、像一位在你身边出谋划策的小伙伴。"
        "善于把用户的长期/模糊计划拆解为具体、可执行且节奏合理的每日事件安排。必须严格返回 JSON。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def plan(context: dict) -> dict:
    """调用 DeepSeek，基于用户的未来计划描述生成事件安排推荐。返回 {insight, schedule:[...], model}。"""
    cfg = load_ai_config()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("未配置 DeepSeek API Key：请检查内置配置（桌面端 deepseek.key 解密是否成功）。")
    import httpx

    base = cfg.get("base_url") or DEFAULT_BASE
    model = cfg.get("model") or "deepseek-chat"
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": _build_plan_messages(context),
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
                "max_tokens": 1400,
            },
            timeout=60,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            detail = ""
        raise RuntimeError(f"DeepSeek 返回错误 {e.response.status_code}：{detail}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"无法连接 DeepSeek：{e}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except Exception:
        return {
            "insight": "",
            "schedule": [{"title": content[:200], "anchor_time": None, "reason": "（来自 DeepSeek 的自由文本）"}],
            "model": model,
            "raw": True,
        }
    sched = parsed.get("schedule") or []
    out = []
    for it in sched:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        at = it.get("anchor_time") or None
        if isinstance(at, str):
            at = at.strip() or None
        out.append({
            "title": title,
            "anchor_time": at,
            "duration_min": _norm_duration(it.get("duration_min")),
            "reason": str(it.get("reason", "")).strip(),
        })
    return {"insight": str(parsed.get("insight", "")).strip(), "schedule": out, "model": model}


def _build_schedule_messages(context: dict) -> list[dict]:
    """基于用户当前情况生成今日完整作息轴推荐。"""
    user_input = (context.get("user_input") or "").strip()
    today = context.get("today") or ""
    weekday = context.get("weekday") or ""
    is_workday = context.get("is_workday")
    location = context.get("location") or ""
    weather = context.get("weather") or ""
    goals = context.get("goals") or []
    planned = context.get("planned") or []
    recent = context.get("recent") or []

    def g(x):
        return x or ""

    goals_txt = "\n".join(
        f"- {g(goal.get('title'))}" + (f"：{g(goal.get('description'))}" if g(goal.get("description")) else "")
        for goal in goals
    ) or "（暂无年度目标）"

    recent_txt = "\n".join(
        f"- [{g(t.get('task_date'))}] {g(t.get('title'))}"
        + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        + (" ✓" if t.get("done") else " ✗")
        for t in (recent or [])[-40:]
    ) or "（暂无历史）"

    planned_txt = "\n".join(
        f"- {g(t.get('title'))}" + (f" @ {g(t.get('anchor_time'))}" if g(t.get("anchor_time")) else "")
        for t in planned
    ) or "（今日暂未排程）"

    workday_line = "工作日" if is_workday is True else ("休息日" if is_workday is False else "未知")

    user = (
        f"今天是 {today}（{weekday}，{workday_line}）。\n\n"
        f"【用户自述情况】\n{user_input or '（未填写）'}\n\n"
        f"【居住地 / 活动地】\n{location or '（未填写）'}\n\n"
        f"【今日天气】\n{weather or '（未填写）'}\n\n"
        f"【年度目标 / 长期方向】\n{goals_txt}\n\n"
        f"【近 30 天行事历史】\n{recent_txt}\n\n"
        f"【今日已排事件】\n{planned_txt}\n\n"
        "请基于上述信息，为用户生成一份完整、合理、可执行的今日作息时间表。要求：\n"
        "1. 覆盖从 00:00 到 24:00 的完整一天，给出 8~15 个连续不重叠的时间段；\n"
        "2. 每个时间段必须包含：开始时间（start_time，HH:MM）、结束时间（end_time，HH:MM）、标签（label，5 字以内中文活动名）、备注（note，20 字以内说明）；\n"
        "3. 充分考虑工作日/休息日差异、天气（如雨雪天调整户外/通勤）、居住地活动、以及用户的计划与目标；\n"
        "4. 不要与「今日已排事件」重复，而是围绕它们进行合理穿插；\n"
        "5. 最后一项请留到睡前，避免熬夜。\n\n"
        "仅输出如下 JSON（不要任何额外文字、不要 markdown 代码块）：\n"
        '{"blocks": [{"start_time": "HH:MM", "end_time": "HH:MM", "label": "活动", "note": "说明"}]}'
    )
    system = (
        "你是「明管家」内置的作息规划小谋士，语气温暖贴心。"
        "你擅长根据用户的身份、居住地、天气、计划和目标，生成一张贴合生活的作息时间表。"
        "必须严格返回 JSON，时间段必须连续覆盖全天。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def schedule(context: dict) -> dict:
    """调用 DeepSeek，基于用户情况生成今日完整作息轴。返回 {blocks:[...], model}。"""
    cfg = load_ai_config()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("未配置 DeepSeek API Key：请检查内置配置（桌面端 deepseek.key 解密是否成功）。")
    import httpx

    base = cfg.get("base_url") or DEFAULT_BASE
    model = cfg.get("model") or "deepseek-chat"
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": _build_schedule_messages(context),
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
                "max_tokens": 1800,
            },
            timeout=60,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            detail = ""
        raise RuntimeError(f"DeepSeek 返回错误 {e.response.status_code}：{detail}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"无法连接 DeepSeek：{e}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except Exception:
        return {
            "blocks": [{"start_time": "00:00", "end_time": "24:00", "label": content[:200], "note": "（来自 DeepSeek 的自由文本）"}],
            "model": model,
            "raw": True,
        }
    blocks = parsed.get("blocks") or []
    out = []
    for it in blocks:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "")).strip()
        if not label:
            continue
        st = str(it.get("start_time") or "").strip() or None
        et = str(it.get("end_time") or "").strip() or None
        out.append({
            "start_time": st,
            "end_time": et,
            "label": label,
            "note": str(it.get("note", "")).strip(),
        })
    return {"blocks": out, "model": model}


def _build_daily_report_messages(context: dict) -> list[dict]:
    """基于某天的真实记录、任务完成情况、金币分布，生成一份温暖有洞察的日报。"""
    date = context.get("date") or ""
    weekday = context.get("weekday") or ""
    actual_records = context.get("actual_records") or []
    tasks = context.get("tasks") or []
    coin_distribution = context.get("coin_distribution") or []

    def g(x):
        return x or ""

    records_txt = "\n".join(
        f"- {g(r.get('start_time'))}–{g(r.get('end_time'))}：{g(r.get('text'))}"
        for r in actual_records
    ) or "（当天没有自由真实记录）"

    tasks_txt = "\n".join(
        f"- [{('✓' if t.get('done') else '✗')}] {g(t.get('title'))}"
        + (f" @ {g(t.get('anchor_time'))}" if g(t.get('anchor_time')) else "")
        + (f" · {g(t.get('category'))}" if g(t.get('category')) else "")
        + (f" · {t.get('duration_min')} 分钟" if t.get('duration_min') else "")
        for t in tasks
    ) or "（当天没有排程任务）"

    coins_txt = "\n".join(
        f"- {g(c.get('category'))}：{round((c.get('coins') or 0), 1)} 金币（{c.get('count', 0)} 项，{(c.get('done_count') or 0)} 项已完成）"
        for c in coin_distribution
    ) or "（当天没有金币消耗记录）"

    done_count = sum(1 for t in tasks if t.get("done"))
    total_count = len(tasks)

    user = (
        f"日期：{date}（{weekday}）。\n\n"
        f"【当天真实记录（自由填写，时间段 + 内容）】\n{records_txt}\n\n"
        f"【当天任务完成情况（✓ 已完成 / ✗ 未完成）】\n共 {total_count} 项，已完成 {done_count} 项。\n{tasks_txt}\n\n"
        f"【当天金币分布（1 金币 = 1 小时，按类目聚合的时间花费）】\n{coins_txt}\n\n"
        "请基于以上信息，为用户写一份温暖、有洞察、像一位贴心小谋士在耳边轻语的「当日日报」。"
        "要求：\n"
        "1. 用 1~2 段自然流畅的中文，不要分点罗列，语气亲切有温度；\n"
        "2. 肯定当天已经完成的事，温和地点出尚未完成的部分；\n"
        "3. 结合金币分布（时间都花在了哪些事上），给出一句关于时间使用的轻反思；\n"
        "4. 结尾用一句鼓励或明日小建议收束；\n"
        "5. 如果出现实记录里有生动细节，适当引用，让日报有真实感。\n\n"
        "仅输出日报正文文本（不要标题、不要 markdown 代码块、不要『日报：』这类前缀）。"
    )
    system = (
        "你是「明管家」内置的可爱谋士，擅长把用户一天的真实记录、任务完成与时间花费，"
        "凝结成一段温暖、真诚、有洞察的当日日报。你像一位懂他朋友，语气俏皮又走心。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def daily_report(context: dict) -> dict:
    """调用 DeepSeek，基于某天的真实记录/任务完成/金币分布，生成当日日报。返回 {report, model}。"""
    cfg = load_ai_config()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("未配置 DeepSeek API Key：请检查内置配置（桌面端 deepseek.key 解密是否成功）。")
    import httpx

    base = cfg.get("base_url") or DEFAULT_BASE
    model = cfg.get("model") or "deepseek-chat"
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": _build_daily_report_messages(context),
                "temperature": 0.8,
                "max_tokens": 900,
            },
            timeout=60,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            detail = ""
        raise RuntimeError(f"DeepSeek 返回错误 {e.response.status_code}：{detail}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"无法连接 DeepSeek：{e}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    report = str(content).strip()
    return {"report": report, "model": model}
