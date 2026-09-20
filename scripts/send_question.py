"""
毎日5問（難易度 1〜5 を易しい順に）、数学I/A/II/B/C から出題し、
Teams ワークフローの Webhook URL に問題カードを送信するスクリプト。

使い方:
  python scripts/send_question.py            # 本番: 5問を Teams に投稿し、出題履歴を更新
  python scripts/send_question.py --dry-run  # 投稿せず、選ばれた問題だけ表示（履歴は更新しない）
  python scripts/send_question.py --check    # 問題データの書式チェックのみ

実行に必要な環境変数（本番時のみ）:
  POWER_AUTOMATE_URL : Teams ワークフローの Webhook URL

一度出題した問題は questions/history.json に記録され、二度と出題されない。
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests

QUESTIONS_DIR = Path(__file__).resolve().parent.parent / "questions"
HISTORY_PATH = QUESTIONS_DIR / "history.json"

# 科目のローテーション順。増減・順序変更はここを編集するだけでよい。
SUBJECT_ORDER = ["math1", "mathA", "math2", "mathB", "mathC"]
LEVELS = [1, 2, 3, 4, 5]  # 1日の出題順（易しい → 標準）
CHOICE_MARKS = ["①", "②", "③", "④"]
POST_INTERVAL_SEC = 3  # Teams 上で問題の順番が入れ替わらないようにする間隔
LOW_STOCK_DAYS = 7  # 残りがこの日数分以下になったら警告する

_SUPERSCRIPT = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")


def pretty(text: str) -> str:
    """x^2 のような簡易表記を x² に変換する（問題文を手で追加するとき用）。"""
    return re.sub(r"\^(-?[0-9]+|n)", lambda m: m.group(1).translate(_SUPERSCRIPT), text)


def load_bank() -> dict[str, list[dict]]:
    bank = {}
    for key in SUBJECT_ORDER:
        with (QUESTIONS_DIR / f"{key}.json").open(encoding="utf-8") as f:
            bank[key] = json.load(f)
    return bank


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


def validate(bank: dict[str, list[dict]]) -> list[str]:
    errors = []
    seen_ids = set()
    for key, questions in bank.items():
        for q in questions:
            qid = q.get("id", "(idなし)")
            if qid in seen_ids:
                errors.append(f"{qid}: id が重複しています")
            seen_ids.add(qid)
            for field in ("subject", "unit", "level", "question", "choices", "answer", "explanation"):
                if field not in q:
                    errors.append(f"{qid}: 項目 {field} がありません")
            choices = q.get("choices", [])
            if len(choices) != len(CHOICE_MARKS):
                errors.append(f"{qid}: 選択肢は {len(CHOICE_MARKS)} 個にしてください")
            if len(set(choices)) != len(choices):
                errors.append(f"{qid}: 同じ選択肢が含まれています")
            if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(choices):
                errors.append(f"{qid}: answer は 0〜{len(choices) - 1} の整数にしてください")
            if q.get("level") not in LEVELS:
                errors.append(f"{qid}: level は {LEVELS} のいずれかにしてください")
    return errors


def stock_table(bank: dict[str, list[dict]], used: set[str]) -> dict[int, int]:
    """難易度ごとの未出題の残り数を返す。"""
    remaining = {level: 0 for level in LEVELS}
    for questions in bank.values():
        for q in questions:
            if q["id"] not in used:
                remaining[q["level"]] += 1
    return remaining


def pick_today(bank: dict[str, list[dict]], history: dict) -> list[dict]:
    """難易度 1〜5 を1問ずつ、易しい順に選ぶ。科目は日ごとにずらして偏りを防ぐ。"""
    used = set(history["used_ids"])
    day = history["day_index"]
    chosen: list[dict] = []
    for level in LEVELS:
        start = (day + level - 1) % len(SUBJECT_ORDER)
        order = SUBJECT_ORDER[start:] + SUBJECT_ORDER[:start]
        for subject in order:
            pool = [q for q in bank[subject] if q["level"] == level and q["id"] not in used]
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


def build_teams_message(question: dict, number: int, total: int) -> dict:
    """Teams ワークフローの Webhook 用に、答え表示ボタン付き Adaptive Card を組み立てる。

    ボタンを押すと、その場で正解/不正解と解説が表示される（サーバー処理は不要）。
    """
    answer = question["answer"]
    choices = [pretty(c) for c in question["choices"]]
    explanation = pretty(question["explanation"])
    stars = "★" * question["level"] + "☆" * (len(LEVELS) - question["level"])

    body = [
        {
            "type": "TextBlock",
            "text": f"📘 今日の数学 Q{number}/{total}　難易度 {stars}",
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"{question['subject']} / {question['unit']}",
            "isSubtle": True,
            "spacing": "None",
            "wrap": True,
        },
        {"type": "TextBlock", "text": pretty(question["question"]), "wrap": True},
        {
            "type": "TextBlock",
            "text": "\n\n".join(f"{CHOICE_MARKS[i]} {c}" for i, c in enumerate(choices)),
            "wrap": True,
        },
    ]

    # 選択肢ごとの結果表示（最初は非表示）
    for i in range(len(choices)):
        if i == answer:
            text = f"✅ 正解です！\n\n{explanation}"
        else:
            text = (
                f"❌ 不正解です。正解は {CHOICE_MARKS[answer]} {choices[answer]}\n\n"
                f"{explanation}"
            )
        body.append(
            {"type": "TextBlock", "id": f"result{i}", "text": text, "wrap": True, "isVisible": False}
        )

    actions = [
        {
            "type": "Action.ToggleVisibility",
            "title": CHOICE_MARKS[i],
            "targetElements": [
                {"elementId": f"result{j}", "isVisible": j == i} for j in range(len(choices))
            ],
        }
        for i in range(len(choices))
    ]

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": body,
                    "actions": actions,
                },
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容だけ表示する")
    parser.add_argument("--check", action="store_true", help="問題データの書式だけ確認する")
    args = parser.parse_args()

    bank = load_bank()
    errors = validate(bank)
    if errors:
        print("問題データにエラーがあります:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    history = load_history()
    used = set(history["used_ids"])
    total = sum(len(v) for v in bank.values())
    print(f"問題データ: 全{total}問、出題済み{len(used)}問")

    if args.check:
        print("書式チェック: OK")
        return

    today = pick_today(bank, history)

    if args.dry_run:
        for i, q in enumerate(today, start=1):
            print(f"Q{i} [{q['id']}] {q['subject']} / {q['unit']} / 難易度{q['level']}")
            print(f"   {pretty(q['question'])}")
        # 本番と同じ組み立て処理を通して、カードが作れることも確認する
        for i, q in enumerate(today, start=1):
            build_teams_message(q, i, len(today))
        print("dry-run: 投稿も履歴の更新もしていません")
        return

    webhook_url = os.environ.get("POWER_AUTOMATE_URL")
    if not webhook_url:
        print("環境変数 POWER_AUTOMATE_URL が設定されていません。", file=sys.stderr)
        sys.exit(1)

    # 5問すべて投稿できてから履歴を更新する（途中失敗で履歴だけ進まないように）
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

    remaining = stock_table(bank, used)
    days_left = min(remaining.values())
    print(f"残りの問題数（難易度別）: {remaining} → あと約{days_left}日分")
    if days_left <= LOW_STOCK_DAYS:
        print(f"::warning::問題の残りが約{days_left}日分です。questions/ に問題を追加してください。")


if __name__ == "__main__":
    main()
