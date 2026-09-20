# content/ — SISIDEN MEDIA の正本データ

STUDIO CMS には**エクスポート機能がない**（2026年9月時点）。
一次情報をSTUDIOだけに置くと、独立ドメインへの移行時や
プラットフォーム変更時にデータを持ち出せなくなる。

このディレクトリはその備えであり、同時に
[Data Connect API](../docs/sisiden-media/integration-toolkit.md) の
データソースでもある。

## 現在入っているもの

**すべてテンプレートであり、実データではない。**
`TODO:` と書かれた値は、取材内容・本人確認を経て差し替えること。

| ファイル | 状態 | 備考 |
|---|---|---|
| `categories/*.yaml` | 確定 | 6カテゴリ。そのまま使える |
| `tags/*.yaml` | 確定 | 初期3タグ |
| `areas/yokohama.yaml` | 公開 | 実在の地名。本文はTODO |
| `organizations/tonkan.yaml` | 下書き | 正式名称の確認が必要 |
| `people/rion-ogura.yaml` | **下書き** | **掲載同意が未取得**。`consent_status: 確認中` |
| `people/sisiden-editorial.yaml` | 下書き | 執筆者用。実名の書き手が決まったら個別に作る |
| `issues/youth-community-space.yaml` | 下書き | `what_we_saw` が書けるまで公開しない |
| `documentaries/tonkan.yaml` | 下書き | タイトルとサブタイトルのみ確定 |
| `articles/tonkan-interview-ogura.yaml` | 下書き | 書き方のサンプルを含む |

## 運用ルール

1. **実在の人物は、掲載同意（`consent_status: 取得済`）がない限り `status: 公開` にしない。**
   `scripts/media_validate.py` がこれを検査する
2. 取材していないことを書かない。`TODO:` を推測で埋めない
3. スラッグは一度決めたら変更しない（URLになるため）
4. STUDIO側で編集した内容は、月1回このディレクトリに反映する

## 使い方

```bash
# 検証（必須項目・参照切れ・孤立ノード・掲載同意）
python scripts/media_validate.py

# STUDIO CMS設定チェックシートを出力
python scripts/media_export.py --format setup

# 記事の一括インポート用 WordPress XML
python scripts/media_export.py --format wxr

# JSON-LD を全ページ分生成
python scripts/media_export.py --format jsonld

# Data Connect API を起動
python scripts/media_serve.py
```

## スキーマ

プロパティ定義は [`config/sisiden_media.yaml`](../config/sisiden_media.yaml) が正本。
設計の根拠は [`docs/sisiden-media/05-studio-cms-model.md`](../docs/sisiden-media/05-studio-cms-model.md)。
