# 高校数学 毎日4択クイズ → Teams配信

数学I・A・II・B・Cの4択問題を毎朝1問、科目を順番にローテーションしながら
Microsoft Teamsのチャネルに自動投稿します。カードの①〜④のボタンを押すと、
その場で正解・不正解と解説が表示されます（サーバー処理は不要）。

## 全体の仕組み

```
GitHub Actions（毎朝7:00 JSTに自動実行）
   └─ scripts/send_question.py が questions/*.json から今日の1問を選ぶ
        └─ Teams「ワークフロー」の Webhook URL にカード付きメッセージをPOST
             └─ Teamsのチャネルに問題カードが投稿される
```

## セットアップ

### 1. GitHubにアップロード済みであること

このリポジトリ（コード一式）がGitHubにあり、Actionsが有効になっている状態にします。

### 2. Teamsのワークフローで Webhook URL を作る

1. Teamsの左端アプリ一覧から **「ワークフロー」** を開く
2. 検索欄に `Webhook` と入力し、**「Webhook アラートをチャネルに送信する」** を選ぶ
   （「特定のユーザーから」「組織内のユーザーから」と付くものは、GitHubから送れないので選ばない）
3. 投稿先の **チーム** と **チャネル** を選んで作成する
4. 完了画面の **「Webhook リンクをコピー」** でURLをコピーする

このURLを知っていれば誰でもそのチャネルに投稿できます。GitHubのSecret以外には保存・共有しないでください。

### 3. GitHubにURLを登録

1. リポジトリの「Settings」→「Secrets and variables」→「Actions」
2. `POWER_AUTOMATE_URL` という名前のシークレットに、手順2でコピーしたURLを登録（既にあれば更新）

### 4. 動作確認

1. リポジトリの「Actions」タブ →「Daily Math Quiz」→「Run workflow」で手動実行
2. Teamsのチャネルにカードが届き、①〜④を押すと正誤と解説が出れば成功です

エラーの場合は「Actions」タブの実行ログに原因が表示されます。

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

- `answer` は正解の選択肢の**番号（0始まり）**です（0=①、1=②…）
- 一度出題した問題は `questions/history.json` に記録され、同じ科目で全問出し切るまで重複しません
- 選択肢は4つにしてください（カードのボタンが①〜④の4つ固定のため）

## 配信時刻・科目の順番を変える

- 配信時刻: `.github/workflows/daily-quiz.yml` の `cron: "0 22 * * *"` を編集
  （UTC基準です。JSTにするには「JSTの時刻-9時間」を指定）
- 科目の順番: `scripts/send_question.py` の `SUBJECT_ORDER` を編集
