"""
数学III クイズ: 毎日3問（極限・微分法・積分法を1問ずつ、易しい順）を Teams に投稿する。

使い方:
  python scripts/send_math3.py            # 本番: 3問を Teams に投稿し、出題履歴を更新
  python scripts/send_math3.py --dry-run  # 投稿せず、選ばれた問題だけ表示（履歴は更新しない）
  python scripts/send_math3.py --check    # 問題データの書式チェックのみ

実行に必要な環境変数（本番時のみ）:
  POWER_AUTOMATE_URL_MATH3 : 数学III用チャネルの Webhook URL

一度出題した問題は questions/history_math3.json に記録され、二度と出題されない。
カード作成・書式チェックは send_question.py（数学I〜C）と共通の部品を使う。
"""

import argparse
import json
import os
import random
import sys
import time

import requests

from send_question import (
    LOW_STOCK_DAYS,
    POST_INTERVAL_SEC,
    QUESTIONS_DIR,
    build_teams_message,
    pretty,
    validate,
)

QUESTIONS_PATH = QUESTIONS_DIR / "math3.json"
HISTORY_PATH = QUESTIONS_DIR / "history_math3.json"

UNITS = ["極限", "微分法", "積分法"]  # 1日に1問ずつ。並びは日ごとにずらす。
SLOT_LEVELS = [1, 3, 5]  # Q1, Q2, Q3 の難易度（易しい → 標準）


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_history() -> dict:
    with HISTORY_PATH.open(encoding="utf-8") as f:
        history = json.load(f)
    used = history.get("used_ids", [])
    return {
        "day_index": int(history.get("day_index", 0)),
        "used_ids": list(used) if isinstance(used, list) else [],
    }


def save_history(history: dict) -> None:
    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")


def validate_math3(questions: list[dict]) -> list[str]:
    errors = validate({"math3": questions})
    for q in questions:
        if q.get("unit") not in UNITS:
            errors.append(f"{q.get('id')}: unit は {UNITS} のいずれかにしてください")
        if q.get("level") not in SLOT_LEVELS:
            errors.append(f"{q.get('id')}: level は {SLOT_LEVELS} のいずれかにしてください")
    return errors


def pick_today(questions: list[dict], history: dict) -> list[dict]:
    """難易度 1, 3, 5 を1問ずつ、易しい順に選ぶ。単元は日ごとにずらして割り当てる。"""
    used = set(history["used_ids"])
    day = history["day_index"]
    chosen: list[dict] = []
    for slot, level in enumerate(SLOT_LEVELS):
        start = (day + slot) % len(UNITS)
        order = UNITS[start:] + UNITS[:start]
        for unit in order:
            pool = [
                q for q in questions
                if q["unit"] == unit and q["level"] == level and q["id"] not in used
            ]
            if pool:
                q = random.choice(pool)
                chosen.append(q)
                used.add(q["id"])
                break
        else:
            raise RuntimeError(
                f"難易度{level}の未出題の問題がなくなりました。問題を追加してください。"
            )
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容だけ表示する")
    parser.add_argument("--check", action="store_true", help="問題データの書式だけ確認する")
    args = parser.parse_args()

    questions = load_questions()
    errors = validate_math3(questions)
    if errors:
        print("問題データにエラーがあります:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    history = load_history()
    used = set(history["used_ids"])
    print(f"数学III 問題データ: 全{len(questions)}問、出題済み{len(used)}問")

    if args.check:
        print("書式チェック: OK")
        return

    today = pick_today(questions, history)

    if args.dry_run:
        for i, q in enumerate(today, start=1):
            print(f"Q{i} [{q['id']}] {q['unit']} / 難易度{q['level']}")
            print(f"   {pretty(q['question'])}")
        for i, q in enumerate(today, start=1):
            build_teams_message(q, i, len(today))
        print("dry-run: 投稿も履歴の更新もしていません")
        return

    webhook_url = os.environ.get("POWER_AUTOMATE_URL_MATH3")
    if not webhook_url:
        print("環境変数 POWER_AUTOMATE_URL_MATH3 が設定されていません。", file=sys.stderr)
        sys.exit(1)

    # 3問すべて投稿できてから履歴を更新する（途中失敗で履歴だけ進まないように）
    for i, q in enumerate(today, start=1):
        if i > 1:
            time.sleep(POST_INTERVAL_SEC)
        response = requests.post(webhook_url, json=build_teams_message(q, i, len(today)), timeout=30)
        response.raise_for_status()
        print(f"送信完了 Q{i}: {q['id']}")

    used.update(q["id"] for q in today)
    history["used_ids"] = sorted(used)
    history["day_index"] += 1
    save_history(history)

    remaining = {
        level: sum(1 for q in questions if q["level"] == level and q["id"] not in used)
        for level in SLOT_LEVELS
    }
    days_left = min(remaining.values())
    print(f"残りの問題数（難易度別）: {remaining} → あと約{days_left}日分")
    if days_left <= LOW_STOCK_DAYS:
        print(f"::warning::数学IIIの問題の残りが約{days_left}日分です。questions/math3.json に問題を追加してください。")


if __name__ == "__main__":
    main()
