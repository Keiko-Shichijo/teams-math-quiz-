"""
毎日1問、数学I/A/II/B/Cを順番にローテーションしながら出題し、
Power Automate の HTTP トリガーに問題データを送信するスクリプト。

実行に必要な環境変数:
  POWER_AUTOMATE_URL : Power Automate フローの「HTTP要求受信時」トリガーのURL

GitHub Actions から1日1回実行される想定。
"""

import json
import os
import random
import sys
from pathlib import Path

import requests

QUESTIONS_DIR = Path(__file__).resolve().parent.parent / "questions"
HISTORY_PATH = QUESTIONS_DIR / "history.json"

# ローテーションする科目の順番。増減・順序変更はここを編集するだけでよい。
SUBJECT_ORDER = ["math1", "mathA", "math2", "mathB", "mathC"]


def load_questions(subject_key: str) -> list[dict]:
    path = QUESTIONS_DIR / f"{subject_key}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_history() -> dict:
    with HISTORY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_history(history: dict) -> None:
    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick_question(subject_key: str, history: dict) -> dict:
    questions = load_questions(subject_key)
    used_ids = set(history["used_ids"].get(subject_key, []))

    candidates = [q for q in questions if q["id"] not in used_ids]
    if not candidates:
        # その科目の問題を全部出し切ったら履歴をリセットして最初から
        used_ids = set()
        candidates = questions

    if not candidates:
        raise RuntimeError(f"{subject_key} に問題が1件も登録されていません。")

    chosen = random.choice(candidates)
    used_ids.add(chosen["id"])
    history["used_ids"][subject_key] = sorted(used_ids)
    return chosen


def build_teams_message(question: dict) -> dict:
    """Teams ワークフローの Webhook 用に、答え表示ボタン付き Adaptive Card を組み立てる。

    ボタンを押すと、その場で正解/不正解と解説が表示される（サーバー処理は不要）。
    """
    marks = ["①", "②", "③", "④"]
    answer = question["answer"]
    choices = question["choices"]

    body = [
        {
            "type": "TextBlock",
            "text": f"📘 今日の数学（{question['subject']} / {question['unit']}）",
            "weight": "Bolder",
            "wrap": True,
        },
        {"type": "TextBlock", "text": question["question"], "wrap": True},
        {
            "type": "TextBlock",
            "text": "\n\n".join(f"{marks[i]} {c}" for i, c in enumerate(choices)),
            "wrap": True,
        },
    ]

    # 選択肢ごとの結果表示（最初は非表示）
    for i in range(len(choices)):
        if i == answer:
            text = f"✅ 正解です！\n\n{question['explanation']}"
        else:
            text = (
                f"❌ 不正解です。正解は {marks[answer]} {choices[answer]}\n\n"
                f"{question['explanation']}"
            )
        body.append(
            {"type": "TextBlock", "id": f"result{i}", "text": text, "wrap": True, "isVisible": False}
        )

    actions = []
    for i in range(len(choices)):
        actions.append(
            {
                "type": "Action.ToggleVisibility",
                "title": marks[i],
                "targetElements": [
                    {"elementId": f"result{j}", "isVisible": j == i}
                    for j in range(len(choices))
                ],
            }
        )

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
    webhook_url = os.environ.get("POWER_AUTOMATE_URL")
    if not webhook_url:
        print("環境変数 POWER_AUTOMATE_URL が設定されていません。", file=sys.stderr)
        sys.exit(1)

    history = load_history()
    cursor = history.get("subject_cursor", 0) % len(SUBJECT_ORDER)
    subject_key = SUBJECT_ORDER[cursor]

    question = pick_question(subject_key, history)
    history["subject_cursor"] = (cursor + 1) % len(SUBJECT_ORDER)
    save_history(history)

    response = requests.post(webhook_url, json=build_teams_message(question), timeout=30)
    response.raise_for_status()
    print(f"送信完了: {question['subject']} / {question['id']}")


if __name__ == "__main__":
    main()
