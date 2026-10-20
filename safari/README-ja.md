# Safariでドメイン名の類似文字を警告する

[English](README.md) | [日本語](README-ja.md)

macOSのSafariで、英字と紛らわしい別の文字がドメイン名に含まれる場合に警告する
Web Extensionです。Unbound版と同じUnicode 17.0.0の対応表1,407件を使います。
異なる文字体系の混在を条件にせず、サブドメインやTLD、複数の英字に対応する文字も検査します。
`аmazon.com` は警告対象ですが、`amazon.com`、`bücher.de`、`日本語.jp` は対象外です。

**通信やページの読み込みを遮断する拡張機能ではありません。**
HTTP・HTTPSのページ上に警告を表示します。Safariのツールバーボタンからは、
ページ上の表示とは独立した判定結果を確認できます。
Punycodeによる実際のドメイン名、Unicodeでの表示、対象文字のコードポイントと対応する英字を示します。
「このページから離れる」を押すと `about:blank` に移ります。
警告を閉じても許可リストには登録されず、再読み込みすると再び表示します。

## Safariで読み込む

`safari/extension` が拡張機能の本体です。npm依存パッケージやビルド処理は不要です。
初期の開発対象はmacOSのSafari 27です。旧版SafariとiOSは未確認です。

Safariの「設定 > デベロッパ」に「一時的な機能拡張を追加」がある場合は、
`safari/extension` を選択してください。未署名の拡張機能に関するSafariの認証手順に従い、
拡張機能を有効にして、検査したいWebサイトへのアクセスを許可します。
一時的な拡張機能は、Safariを終了するか24時間経過すると削除されます。

macOSアプリとして組み込む場合は、Xcodeを用意し、リポジトリのルートで実行します。

```sh
python3 scripts/fetch_confusables.py
sh scripts/package_safari.sh
xcodebuild -project build/safari/AntiHomograph/AntiHomograph.xcodeproj \
  -scheme AntiHomograph -configuration Debug \
  -derivedDataPath build/safari-derived CODE_SIGNING_ALLOWED=NO build
```

生成先に既存プロジェクトがある場合、スクリプトは上書きせず停止します。
生成したプロジェクトは `safari/extension` を参照するため、通常の変更では再ビルドだけで更新されます。
リソースファイルを追加・削除した場合は、プロジェクトを生成し直してください。
Xcodeで生成したプロジェクトを開き、アプリを実行して拡張機能を登録してください。
配布用に署名するときは、自分のBundle Identifierと開発チームを設定します。
未署名のローカル開発は、Appleの説明に従ってSafariで許可してください。
このリポジトリのスクリプトは、Safariの設定変更、アプリのインストール、拡張機能の有効化を行いません。

ページ上の自動警告には、Webサイトへのアクセス許可が必要です。
広く検査する場合は「すべてのWebサイト」で許可し、対象を限定する場合はサイトごとに許可します。
インストールしただけではアクセスは許可されません。
ツールバーボタンを押した際の `activeTab` 権限で判定できても、
すべてのサイトで自動警告が有効になっているとは限りません。
Safariのプロファイルとプライベートブラウズの権限も個別に確認してください。

## 判定とプライバシーの範囲

拡張機能による外部通信、利用状況の収集、バックグラウンド処理、Cookieの利用、
閲覧履歴や例外設定の保存は行いません。検査するのは現在のページのホスト名だけです。
URLのパスやクエリ文字列は表示も保存もしません。判定用のデータは同梱しています。

警告が出る前に、サイトの読み込みやスクリプトの実行が始まる場合があります。
ページ上の警告は閉じたShadow DOMでスタイルを分離していますが、
悪意あるサイトが削除したり、覆い隠したり、似た表示を作ったりすることは防げません。
拡張機能側の判定を確認するときは、Safariのツールバーボタンを使ってください。
リンク先、フレーム、画像などの追加リソース、CNAME、ダウンロード、ほかのアプリは検査しません。
Safariが拡張機能の実行を制限するページや、アクセスを許可していないサイトでは自動警告が出ません。

正当なドメイン名も警告対象になる場合があります。
「判定対象の文字は見つかりませんでした」という結果は、安全性の保証ではありません。
ASCII文字だけの偽装、多くのアクセント付き文字、その他のフィッシング手法は対象外です。
また、SafariがURLを解析する段階で拒否・正規化した名前は、そのまま検査できません。
検査時点で残っている不正・非正規形のPunycodeは警告しますが、IDNAの完全な妥当性検査は行いません。

## 判定データを更新する

Node.js 22以降とPython 3を使います。

```sh
python3 scripts/fetch_confusables.py
python3 scripts/build_safari_data.py
python3 scripts/build_safari_data.py --check
node --test tests/safari.test.cjs
```

生成スクリプトは取得元のSHA-256を検証し、Pythonフィルタの `parse_confusables` を再利用します。
Unicodeのバージョンを更新した際は、生成した `confusables.js` もコミットしてください。
テストでは全対応文字と追加のラベルについてPython版と判定を比較し、
簡易なDOM・ブラウザAPIの代替実装で警告とポップアップの処理を確認します。
Safariのアクセス許可やVoiceOverの動作を再現するテストではありません。

macOSでは `swift tests/safari_webkit.swift` で、実際のWebKitによる描画、
フォーカス、警告を閉じる操作も確認できます。
拡張機能のAPIは代替実装を使い、テスト用サイトには接続しません。
画像は `build/safari-webkit` に出力します。Safariへの登録や有効化は行いません。

独自に描いたPNGの盾アイコンは、macOSで
`swift scripts/build_safari_icons.swift` を実行すると再生成できます。
配布時もコードの `extension/LICENSE.txt` と、
Unicodeデータの `extension/UNICODE-LICENSE.txt` を残してください。

2026年10月20日時点では、macOS 27.0.1・Xcode 27.1で未署名アプリをビルドしました。
全1,407対応文字と追加407ラベルはPython版と判定が一致しています。
WebKitでは日本語・英語、明暗、200%ズーム、フォーカス、警告を閉じる操作を含む
7シナリオを実行し、出力画像も確認しました。
Safari 27.0.1はインストールされていますが、拡張機能の登録、Safariの権限設定、
実際のキーボードによる巡回、VoiceOverは未確認です。配布用の署名も行っていません。

リリース前にはSafariで、インストールとアクセス許可、Unicode・Punycode両表記のアドレス、
警告の二つのボタン、権限拒否、プロファイル、プライベートブラウズを確認してください。
ダークモード、キーボード操作、200%ズーム、VoiceOverも確認が必要です。
自動警告はフォーカスを奪わず、モーダルダイアログを開きません。
色だけに頼らず文章で警告し、アニメーションは使いません。
Web UIとして意味のあるHTML要素を使っており、macOSのネイティブ警告ではありません。

## 既存製品の調査と設計根拠

2026年10月20日にWeb、Mac App Store、GitHubの公開プロジェクトを検索した範囲では、
この種の警告に特化したSafari拡張機能は確認できませんでした。不在を証明するものではありません。
Chrome向けには
[Unicode Domain Warning](https://chromewebstore.google.com/detail/unicode-domain-warning/khijgpndoffkmanglickjbnkbjimcdhn)
があります。

Appleの実装資料、HIGの参照先と用途は[英語版の出典表](README.md#research-and-primary-references)に記載しています。
警告、根拠となるドメイン名、ページから離れる操作、今回だけ閉じる操作、ツールバーからの判定確認に絞りました。
日本語・英語はSafariのUI言語に従い、明暗の表示はシステム設定に従います。
外部のフォント、画像、フレームワーク、サービスは不要です。
