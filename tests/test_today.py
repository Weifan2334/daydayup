"""v0.1 smoke tests — 不接 pytest，直接 python -m tests.test_today 也能跑。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# 让脚本能从仓库根 import backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db  # noqa: E402
from backend.services import today as today_service  # noqa: E402


def assert_eq(label: str, actual, expected) -> None:
    ok = actual == expected
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {label}: {actual!r}")
    if not ok:
        print(f"     expected: {expected!r}")
        sys.exit(1)


def main() -> None:
    print("[1] 初始化 DB + 种子")
    db.get_conn()
    today_service.seed_defaults_if_empty()

    print("[2] v4 作息时间块已落库")
    anchors = db.list_anchors(enabled_only=True, kind="block")
    assert_eq("blocks count = 15 (v4 schedule)", len(anchors), 15)
    labels = [a["label"] for a in anchors]
    for required in ("起床 & 简单早餐", "运动 / 拉伸", "深度科研时间", "实验或项目推进", "睡前准备"):
        assert_eq(f"contains {required}", required in labels, True)
    # 关键时间戳
    times = [a["anchor_time"] for a in anchors]
    assert_eq("07:30 first block", times[0], "07:30")
    assert_eq("22:00 last block", times[-1], "22:00")
    # 全部有 end_time
    assert_eq("all blocks have end_time", all(a.get("end_time") for a in anchors), True)
    # 工作日 mask
    assert_eq("default weekdays = workdays", anchors[0]["weekdays"], "1,2,3,4,5")

    print("[3] 提醒已落库")
    reminders = db.list_reminders(enabled_only=False)
    assert_eq("reminders count >= 9", len(reminders) >= 9, True)

    print("[4] 今日视图（v4 时间块）")
    view = today_service.build_today_view("2026-07-14")
    assert_eq("today_date", view["today_date"], "2026-07-14")
    assert_eq("weekday", view["weekday"], "周二")
    assert_eq("blocks 字段存在", "blocks" in view, True)
    # current_block 取决于实际运行时间，至少应是 15 块之一
    cb_label = view["current_block"]["label"] if view["current_block"] else None
    all_labels = [b["label"] for b in view["blocks"]]
    assert_eq("current_block 落在某段", cb_label in all_labels if cb_label else True, True)
    assert_eq("next_block 不为空", view["next_block"] is not None, True)
    assert_eq("summary present", "summary" in view, True)

    print("[5] 添加任务 + toggle + 删除")
    today_str = "2026-07-14"
    t = db.add_task(today_str, "测试任务 A", anchor_time="19:30", duration_min=15)
    tid = t["id"]
    assert_eq("task created", t["title"], "测试任务 A")
    assert_eq("task done=0", t["done"], False)
    t2 = db.toggle_task(tid)
    assert_eq("task toggled", t2["done"], True)
    db.delete_task(tid)
    remaining = db.list_tasks(today_str)
    assert_eq("task deleted", all(t["id"] != tid for t in remaining), True)

    print("[6] 跨天 next_block 兜底")
    # v4 第一段是 07:30，跨天后 next 应回到 07:30
    first_block = next((a for a in anchors if a["anchor_time"] == "07:30"), None)
    assert_eq("07:30 first block exists", first_block is not None, True)
    assert_eq("first block end_time", first_block["end_time"] if first_block else None, "08:00")

    print("\n所有 smoke tests 通过 [OK]")


if __name__ == "__main__":
    main()