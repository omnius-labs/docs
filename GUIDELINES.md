# GUIDELINES

## Products ページ

`content.ja/docs/products/` に、所属ごとの階層を作り、その下にプロダクトごとのページを置く。

### 構成

- `_index.md`: 全体の一覧ページ。所属ページへのリンクを並べる。
- `<owner>/_index.md`: 所属（`omnius-labs`、`lyrise`）のページ。所属するプロダクトの一覧表を置く。`<owner>` は GitHub の owner 名と一致させる。
- `<owner>/<name>/_index.md`: プロダクトのページ。`<name>` は GitHub のリポジトリ名（kebab-case）と一致させる。
- 所属が変わったら、ページを移動する。URL も変わるので、その点は許容する。
- サイドバーの順序は各ページの `weight` で決める。所属ページの表に並べた順と一致させる。
- `weight` は所属の中で 10 刻みにして、間にプロダクトを挿入できる余地を残す。

### 命名

- `title` はリポジトリ名をそのまま使う（例: `image-classifier` → `image-classifier`）。語を分けたり大文字にしたりしない。
- omnius-labs のプロダクトは製品名として扱い、先頭を大文字にする（例: `axus` → `Axus`）。

### ページの章立て

冒頭に情報表を置き、続けて次の章をこの順に並べる。中身のない章は、章ごと省略する。

| 章 | 内容 |
| --- | --- |
| （情報表） | 種別、リポジトリ、公開範囲、ステータス。ライセンスがあれば追加する |
| Goal | 何を実現するプロダクトか |
| Why | なぜ開発するのか |
| Features | 提供する機能 |
| Usage | 使い方（CLI など、利用手順があるもの） |
| Downloads | 配布物がある場合のみ。`scripts/sync-releases.py` が shortcode を挿入する |
| Links | 関連リンク |

- 公開範囲は、パブリック / プライベートと、オープンソース / クローズドソースを併記する。
- プライベート repo へのリンクは、権限のない読者には 404 になる。リポジトリ欄には載せ、説明はページ内で完結させる。

## 配布物

配布物は GitHub Release に上げ、`scripts/sync-releases.py` が Cloudflare R2 へミラーする。
private repo の Release は公開できないため、公開は R2 が担う。
Downloads 章は `data/releases.json` から自動で描画されるので、手で書かない。

### 置き場所

- キー: `<product>/<tag>/<file>`
- 公開 URL: `https://downloads.omnius-labs.org/<product>/<tag>/<file>`

公開 URL の起点は `config.yaml` の `params.downloadsBaseURL` に置く。
state に絶対 URL は持たせないので、配信先を変えるときはこの 1 行だけを直せばよい。

配信は、R2 バケットに接続したカスタムドメイン `downloads.omnius-labs.org` が担う。
このドメインは Cloudflare Registrar で取得し、ゾーンを R2 と同じ Cloudflare アカウントで
管理している。カスタムドメインを使うにはこの条件を満たす必要があり、
ゾーンを他社 DNS に置いたままでは Business プラン以上を要する。

### 手順

1. プロダクトの repo で Release を作り、配布物を資産として添付する。
2. 新しいプロダクトなら `releases.toml` に登録する。
3. `./scripts/sync-releases.py` を実行する。

R2 へのアップロード、`data/releases.json` の更新、Downloads 章の追加までこれで済む。
ツールは git を操作しないので、差分を確認してから commit する。

`--dry-run` で予定だけを出力できる。`--product <name>` で対象を絞れる。

### 対象の決まり

- draft は常に対象外とする。prerelease は `releases.toml` の `prerelease` で切り替える。
- 資産は `assets` のグロブ（既定は `*.zip`）で絞る。一致しない資産は無視する。
- GitHub 側で Release や資産を消しても、R2 と表からは消えない。消すときは R2 と `data/releases.json` を手で直す。

### state

- `data/releases.json` が同期の記録であり、Hugo のデータ源でもある。ツールが書くので手で編集しない。
- state に無い資産は、アップロードの前に R2 の実体を確認する。state を消しても、R2 にあるものは再アップロードされない。

### 認証情報

- R2 の認証情報は、この repo に含めない。`.envrc.example` を `.envrc` にコピーして値を埋める（`.envrc` は gitignore 済み）。
- GitHub へのアクセスは `gh` に任せる。あらかじめ `gh auth login` を済ませる。

## リポジトリ

- この repo は public とする。サイトは全ページ公開で、公開範囲の制御は行わない。
- Netlify の無料プランは組織所有の private repo では継続的デプロイができない。private には戻さない。
- hugo-book の「最終更新」「編集」リンクは無効にしている（`config.yaml` の `enableGitInfo`、`BookRepo`、`BookEditPath`）。
