# SISIDEN Relationship OS

営業と広報を分離せず、「人物」を中心に名刺・メール・案件・メディア・営業履歴を
1つのDBへ統合する、株式会社シシクリエイションの関係資産管理システム。

> 名刺は名刺として保存しない。人との関係を会社の資産にする。
> プレスリリースは配信して終わりにしない。コンテンツ、人脈、営業、メディアリレーションへ展開する。
> 営業と広報を別部署の仕事として設計しない。

既存の「[SISIDEN 全国自治体案件ハンター](../README.md)」(`src/collectors` 以下、官公需案件の収集・スコアリング)
とは別モジュール・別DBファイルとして共存する。技術スタック(Python 3.11 / SQLite / 生SQL /
`mcp==2.2.0` の `MCPServer` / argparse CLI)はそのまま踏襲し、新しい依存は追加していない。

## 1. 現在のシステム構造(要約)

| 項目 | 内容 |
|---|---|
| 言語/実行環境 | Python 3.11、依存は `requirements.txt`(標準的なPythonのみ、フレームワーク非依存) |
| DB | SQLiteを生SQLで操作(`src/database/db.py` が既存の型)。ORM不使用、将来のPostgreSQL移行を想定した書き方 |
| MCP | `mcp==2.2.0` の `mcp.server.mcpserver.MCPServer`。`@mcp.tool(description=...)` でツール登録、STDIOトランスポート |
| CLI | `argparse` ベースのスクリプトを `scripts/` に配置 |
| AI方針 | 収集・スコアリング・検索はルールベース。高度な判断・文章生成はMCPクライアント(Claude)側 |

この構成が今回の用途(人物中心のリレーションシップDB)にもそのまま適合するため、
別の技術スタックは導入せず、既存パターンを複製する形で `src/relationship/` を追加した。

## 2. ディレクトリ構成(追加分)

```
src/relationship/
  database/
    schema.sql        DBスキーマ(persons中心、12テーブル)
    db.py              CRUD・重複判定・検索・キャンペーンフロー
  importers/
    common.py           CSVヘッダー自動マッピング・dedup連携ヘルパー
    eight_csv.py          Eightエクスポートcsvインポーター
    generic_csv.py         既存営業リスト/メディア・記者リスト用汎用インポーター
  matching/
    scorer.py                Project→人物のルールベーススコアリング(100点満点)
  mcp/
    server.py                  MCP Server本体(21ツール)
    tools.py                    ツールのビジネスロジック
scripts/
  init_relationship_db.py        DB初期化
  import_eight_csv.py             Eight CSVインポート実行
  import_csv.py                    汎用CSVインポート実行
tests/
  test_relationship.py             自動テスト(11件、実データで検証済み)
  relationship_fixtures/            サンプルCSV(Eight/営業リスト/メディアリスト)
docs/relationship_os.md            本ドキュメント
data/sisiden_relationship.db       SQLite DB(gitignore対象、init_relationship_db.pyで生成)
```

自治体案件ハンターの `opportunities.db` とは物理的に別ファイル。
`projects.opportunity_id` に自治体案件ハンター側の `opportunities.id` を
FK制約なしで保持できるようにしており、将来「自治体案件が実際の映像案件になった」
場合に紐付けられる設計にしてある(現時点では未接続、拡張ポイントとして予約)。

## 3. DBスキーマ(ER概要)

```
organizations ──┬─< persons >──┬─< person_tags >── tags
                │               ├─< media_profiles (1:1)
                │               ├─< interactions >── projects
                │               ├─< campaign_targets >── campaigns >── campaign_audiences
                │               ├─< coverage >── projects
                │               ├─< person_sources
                │               └─< duplicate_candidates (self-referencing pair)
                └─< coverage
projects ──< contents
projects ──< campaigns
import_batches ──< person_sources (取込監査ログ)
```

主要テーブルとその役割は [`src/relationship/database/schema.sql`](../src/relationship/database/schema.sql) の
コメントを参照。フィールド定義はユーザー要件のPERSON/ORGANIZATION/MEDIA_PROFILE/PROJECT/
INTERACTION/CAMPAIGN/CONTENT/COVERAGEにほぼ1対1で対応させている。

### 重複防止(dedup)の方針

1. **メールアドレス完全一致(正規化: trim+lower)** → 同一人物と確定。新規行を作らず既存行を更新する。
2. **電話番号 / 氏名+会社名 / 氏名+部署 の一致** → 確信度が低いため自動統合しない。
   新規行は作成した上で `duplicate_candidates` に候補として記録し、
   `list_duplicate_candidates` / `resolve_duplicate` MCPツールで人間が確認・統合・却下する。
3. 削除は原則行わない。重複統合時のみ、統合された側を `is_deleted=1` + `merged_into_id` で
   論理削除する(監査可能な形で残す)。

## 4. データフロー

```
Eight CSV ─┐
既存営業リストCSV ─┼─> importers/*.py ─> db.upsert_person() [dedup判定] ─> persons/organizations/tags/interactions
メディア・記者CSV ─┘

Project登録(create_project)
   └─> matching/scorer.py: recommend_people_for_project()
         ルールベーススコア(テーマ30/業界20/関係性20/最近の接触10/地域10/過去反応10)
         → MEDIA / SALES / RELATIONSHIP / AMPLIFICATION に分類 + 理由文
   └─> Claude が文面案(記者Pitch/営業メール/SISIDEN LETTER/Web記事)を生成
   └─> add_campaign_targets(draft_text含む) … STEP6: 人間が候補・文面を確認
   └─> update_campaign_target_status(status="approved"→"sent") … 人間が実際に送信した「事実」を記録
         └─> status="sent" になった瞬間、Interactionが自動生成される(STEP8: 資産化)
```

外部送信の実行そのもの(メールを実際に配信する処理)はこのシステムに実装していない。
これは意図的な設計であり、要件15「AIによる自動送信は禁止」を技術的に担保するため。

## 5. Gmail連携について(現状と設計)

MVP1〜2の時点ではGmail APIとの実接続は実装していない(認証情報の取り扱いが必要なため、
別途ユーザー環境でのOAuth設定が前提になる)。ただし、スキーマ・MCPツールはGmail連携を
そのまま受け止められる形にしてある:

- `interactions` テーブルの `channel='email'` で、Gmail起点のやり取りをそのまま記録できる。
- `log_interaction` ツールは「メール本文の要約」を `summary` に、返信の有無を `reaction` に
  記録する設計であり、本文全体を永続保存しない(要件どおり)。
- 将来、Gmail APIから同期するバッチ(`scripts/sync_gmail.py` を想定)を追加する場合、
  やることは「Gmail検索 → 相手のメールアドレスで `persons` を特定(または`create_person`で新規) →
  `log_interaction` を呼ぶ」だけで、DBスキーマの変更は不要。
- 送信(下書き作成含む)を自動化する場合も、Claudeが下書きを生成 → 人間が確認 → 実際の送信は
  人間 or Gmail側で実施 → 結果を `log_interaction` / `update_campaign_target_status(status="sent")`
  で記録、という同じ承認フローに乗せる。

## 6. UI構成(現状はMCP経由、将来のダッシュボード画面を想定)

MVP1〜2では管理画面(Webフロントエンド)は実装せず、Claude Desktop/Claude Code等の
MCPクライアントから自然言語で操作する形をUIとしている(既存の自治体案件ハンターと同じ思想)。
`get_dashboard` ツールが返す構造は、将来Next.js等でダッシュボード画面を作る際にそのまま
API応答として使える形にしてある:

- 進行中Project / 今週連絡すべき人(7日以内フォローアップ) / 重要なのに180日以上未接触の人物 /
  最近返信があった人物 / 最近のメディア掲載 / 今月のCampaign / 未解決の重複候補件数

案件登録画面(STEP1〜8)のバックエンドAPIは `create_project` → `recommend_people_for_project` →
`create_campaign`/`add_campaign_audience` → `add_campaign_targets` → `update_campaign_target_status`
の呼び出し順序としてすでに実装済み。フロントエンドを追加する場合、この順序をそのまま
ウィザードUIのステップに対応させられる。

## 7. MVPロードマップ

| フェーズ | 内容 | ステータス |
|---|---|---|
| **MVP1** | Person/Organization/Project/Interaction/Tag DB、Eight CSV import、既存CSV import、重複チェック、人物検索、案件検索 | **実装済み** |
| **MVP2** | Project→人物候補抽出、MEDIA/SALES/RELATIONSHIP/AMPLIFICATION分類、Claude自然言語検索、キャンペーン承認フロー(文章生成はClaude側) | **実装済み**(MCPツール21種) |
| **MVP3** | Gmail連携(過去メールからInteraction生成・下書き作成・送信後Interaction自動記録) | 未実装(§5の設計に沿って`log_interaction`/`create_person`を呼ぶバッチとして追加予定) |
| **MVP4** | メルマガ配信サービス連携(開封/クリック/配信停止の取り込み)、SISIDEN Webメディア連携、掲載実績分析ダッシュボード(Web UI) | 未実装 |

## 8. 使い方

```bash
# 1. DB初期化
python scripts/init_relationship_db.py

# 2. Eightエクスポートcsvを取り込む
python scripts/import_eight_csv.py --file eight_export.csv

# 3. 既存営業リスト/メディアリストを取り込む
python scripts/import_csv.py --file sales_list.csv --source csv_sales --org-type municipality
python scripts/import_csv.py --file press_list.csv --source csv_media --tags "記者" --media

# 4. MCP Serverを起動(Claude Desktop/Claude Code等のmcpServers設定に登録)
python src/relationship/mcp/server.py
```

Claude Desktop/Claude Codeの設定例:

```json
{
  "mcpServers": {
    "sisiden-relationship-os": {
      "command": "python",
      "args": ["/absolute/path/to/sisiden-hunter/src/relationship/mcp/server.py"]
    }
  }
}
```

自治体案件ハンターのMCPサーバー(`sisiden-opportunity-mcp`)と同時に登録して併用できる。

## 9. テスト

```bash
python tests/test_relationship.py
# または
python -m pytest tests/test_relationship.py -v
```

重複判定(メール自動統合/電話・氏名一致の候補化/統合マージ)、CSVインポート(Eight/営業リスト/
メディアリスト)、Interaction記録による関係性強度・最終接触日の更新、Project→人物レコメンド
(MEDIA/SALES/RELATIONSHIP/AMPLIFICATION分類とオプトアウト除外)、MCPツール経由のキャンペーン
承認フロー(候補抽出→承認→送信→Interaction自動生成)、自然言語検索相当のフィルタ、
ダッシュボード集計、重複候補レビューを一通り検証している(11テスト、実データで通過確認済み)。

## 10. 個人情報保護についての現状

- DBファイル(`data/sisiden_relationship.db`)は `.gitignore` 対象(既存の`opportunities.db`と同様)。
- オプトアウト(`newsletter_status`/`sales_email_status`/`media_pitch_status`)が
  `unsubscribed`/`do_not_contact` の人物は、`recommend_people_for_project` の候補抽出から
  必ず除外される(スコアリングエンジン内でハード除外、Claude側での回避不可)。
- 重複統合以外での人物削除は論理削除(`is_deleted`)を想定しており、物理削除APIは未実装
  (本人からの削除依頼への対応は今後の検討事項)。
- 認証・アクセス制御・監査ログ・バックアップは、MVP1〜2の時点ではMCPのローカルSTDIO実行
  (既存の自治体案件ハンターと同じ運用)を前提としており、複数ユーザーでの共有運用や
  リモートMCP化を行う場合は別途認証層の追加が必要(既存READMEの「ChatGPT Web等」の節と同様の課題)。
