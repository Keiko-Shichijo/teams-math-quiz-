# 高校数学 毎日4択クイズ → Teams配信

数学I・A・II・B・Cの4択問題を毎朝1問、科目を順番にローテーションしながら
Microsoft Teamsのチャネルに自動投稿し、選択肢をボタンで回答すると
その場で正誤と解説が返ってくる仕組みです。

## 全体の仕組み

```
GitHub Actions（毎朝7:00 JSTに自動実行）
   └─ scripts/send_question.py が questions/*.json から今日の1問を選ぶ
        └─ Power Automate の「HTTP要求受信時」フローにPOST
             └─ Adaptive Card（4択ボタン付き）をTeamsチャネルに投稿
                  └─ ボタンが押されたら正誤判定して返信
```

コードはすべて用意済みです。あなたにやっていただく作業は次の3つだけです。

1. GitHubにこのフォルダをアップロードする
2. Power Automateでフローを1つ作る（コピペ中心、下に手順あり）
3. GitHubにPower AutomateのURLを1つ登録する

---

## 手順1. GitHubにアップロード

1. https://github.com でアカウントを作成（お持ちなら不要）
2. 右上の「+」→「New repository」で新しいリポジトリを作成
   （例: `teams-math-quiz`、Public/Privateどちらでも可）
3. このフォルダ（`teams-math-quiz`）の中身をアップロード
   - GitHubの画面で「Add file」→「Upload files」からドラッグ＆ドロップでもOK
   - Gitコマンドが使える場合は以下でも可
     ```bash
     git init
     git add .
     git commit -m "initial commit"
     git branch -M main
     git remote add origin https://github.com/<あなたのアカウント>/teams-math-quiz.git
     git push -u origin main
     ```

## 手順2. Power Automateでフローを作る

1. https://make.powerautomate.com を開く（会社/学校のMicrosoft 365アカウントでログイン）
2. 「作成」→「インスタントクラウドフロー」→ 名前を付けて
   トリガーに **「HTTP要求の受信時」(When a HTTP request is received)** を選択
3. トリガーの「要求本文のJSONスキーマ」に以下を貼り付け

   ```json
   {
     "type": "object",
     "properties": {
       "subject": { "type": "string" },
       "unit": { "type": "string" },
       "question": { "type": "string" },
       "choices": { "type": "array", "items": { "type": "string" } },
       "answerIndex": { "type": "integer" },
       "explanation": { "type": "string" }
     }
   }
   ```

4. 新しいステップを追加 →「Microsoft Teams」コネクタ →
   **「Post adaptive card and wait for a response」
   （アダプティブ カードを投稿して応答を待機）** を選択
   - 投稿者: Flow bot（またはご自身）
   - 投稿先: Channel（チャネル）
   - チーム / チャネル: 配信したいチームとチャネルを選択
   - 「Adaptive Card」欄の右上にあるコードアイコン（`</>`）を押して
     JSON編集モードに切り替え、以下を貼り付け

   ```json
   {
     "type": "AdaptiveCard",
     "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
     "version": "1.4",
     "body": [
       {
         "type": "TextBlock",
         "text": "📘 今日の数学問題（@{triggerBody()?['subject']} / @{triggerBody()?['unit']}）",
         "weight": "Bolder",
         "wrap": true
       },
       {
         "type": "TextBlock",
         "text": "@{triggerBody()?['question']}",
         "wrap": true
       }
     ],
     "actions": [
       { "type": "Action.Submit", "title": "① @{triggerBody()?['choices']?[0]}", "data": { "choice": 0 } },
       { "type": "Action.Submit", "title": "② @{triggerBody()?['choices']?[1]}", "data": { "choice": 1 } },
       { "type": "Action.Submit", "title": "③ @{triggerBody()?['choices']?[2]}", "data": { "choice": 2 } },
       { "type": "Action.Submit", "title": "④ @{triggerBody()?['choices']?[3]}", "data": { "choice": 3 } }
     ]
   }
   ```

5. 新しいステップ →「制御」→ **「条件」(Condition)** を追加
   - 左辺の入力欄に、`fx`（式）から以下を貼り付け
     ```
     outputs('Post_adaptive_card_and_wait_for_a_response')?['body/data']?['choice']
     ```
     （アクション名を変更した場合はカッコ内の名前も合わせて変更してください）
   - 演算子: 「次の値に等しい」
   - 右辺:「動的なコンテンツ」から トリガーの `answerIndex` を選択

6. 「はいの場合」に「Microsoft Teams」→「投稿するメッセージ」を追加し、
   投稿先を同じチーム/チャネルにして本文に
   ```
   ✅ 正解です！
   @{triggerBody()?['explanation']}
   ```
7. 「いいえの場合」にも同様にメッセージ投稿を追加し
   ```
   ❌ 不正解です。正解は選択肢 @{add(triggerBody()?['answerIndex'], 1)} でした。
   @{triggerBody()?['explanation']}
   ```
8. フローを保存し、トリガーの「HTTP要求の受信時」を開いて
   表示される **URL** をコピー（`https://prod-xx.japaneast.logic.azure.com/...` のような形式）
   → これを手順3で使います

## 手順3. GitHubにURLを登録

1. GitHubのリポジトリ画面で「Settings」→「Secrets and variables」→「Actions」
2. 「New repository secret」を押し
   - Name: `POWER_AUTOMATE_URL`
   - Secret: 手順2の最後でコピーしたURL
3. 保存

## 動作確認

1. リポジトリの「Actions」タブ →「Daily Math Quiz」を選択
2. 「Run workflow」ボタンで手動実行
3. Teamsのチャネルにカードが届き、ボタンを押すと正誤判定が返ってくれば成功です

エラーが出た場合は「Actions」タブの実行ログに原因が表示されます
（多くは `POWER_AUTOMATE_URL` の設定ミスか、フロー側のアクション名の不一致です）。

---

## 問題の追加方法

`questions/` フォルダの中に科目ごとのJSONファイルがあります。

| ファイル | 科目 |
|---|---|
| `math1.json` | 数学I |
| `mathA.json` | 数学A |
| `math2.json` | 数学II |
| `mathB.json` | 数学B |
| `mathC.json` | 数学C |

以下の形式でオブジェクトを配列に追加していけば増やせます。`id`は同じファイル内で重複しない文字列にしてください。

```json
{
  "id": "math1-003",
  "subject": "数学I",
  "unit": "二次関数",
  "question": "問題文をここに書く",
  "choices": ["選択肢1", "選択肢2", "選択肢3", "選択肢4"],
  "answer": 0,
  "explanation": "解説文をここに書く"
}
```

- `answer` は正解の選択肢の**番号（0始まり）**です（0=1番目、1=2番目…）
- 一度出題した問題は `questions/history.json` に記録され、同じ科目で全問出し切るまで重複しません
- ファイルを更新したら、GitHubにpush（またはアップロード）するだけで翌日以降の配信に反映されます

## 配信時刻・科目の順番を変える

- 配信時刻: `.github/workflows/daily-quiz.yml` の `cron: "0 22 * * *"` を編集
  （UTC基準です。JSTにするには「JSTの時刻-9時間」を指定）
- 科目の順番: `scripts/send_question.py` の `SUBJECT_ORDER` を編集
