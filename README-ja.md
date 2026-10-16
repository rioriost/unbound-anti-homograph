# Unbound ホモグラフ対策フィルタ

[English](README.md) | [日本語](README-ja.md)

Unicodeの類似文字対応表（confusables）でASCII英字に対応付けられる非ASCII文字を、
国際化ドメイン名（IDN）のラベルが含む場合に、DNS問い合わせを拒否します。
保護対象のブランド名と比較する方式ではなく、文字そのものを対象とする厳格なポリシーです。

**修正済みのPython対応Unboundが必要です。標準のUnboundだけでは使えません。**
フィルタはUnbound本体の対応状況を示すマーカーを検査し、未対応のビルドでは初期化を停止します。
稼働中のリゾルバを変更する前に、前提条件を確認してください。

## 拒否する名前

問い合わせ名のうち、大文字・小文字を区別せず `xn--` で始まるすべてのラベルを、
Punycodeから復号します。復号した非ASCII文字の中に、対応先が `A-Z` または `a-z` だけで
構成される文字が一つでもあれば、問い合わせを拒否します。
`rn` のように複数の英字に対応する場合も対象です。
異なる文字体系の混在は条件にしません。同じ文字体系だけで構成されたラベル、
サブドメイン、トップレベルドメイン（TLD）も検査します。
壊れたPunycodeや、正規の表記ではないPunycodeラベルも拒否します。

| 名前 | フィルタの判定 |
| --- | --- |
| `amazon.com` | 許可 |
| `аmazon.com`（先頭がキリル文字 U+0430。`xn--mazon-3ve.com`） | 拒否 |
| `ı.example`（ドットなしのラテン文字i、U+0131） | 拒否 |
| `〇.example`（漢数字のゼロ、U+3007） | 拒否 |
| `bücher.de` / `日本語.jp` | 許可 |

Unicode 17.0.0の対応表には、この条件を満たす対応付けが **1,407件**あります。
取得元のコミットとSHA-256は
[`scripts/fetch_confusables.py`](scripts/fetch_confusables.py) で固定しています。
DNS問い合わせの処理中にデータをダウンロードすることはありません。

正当な外国語の名前でも、対象文字を含めば拒否します。許可リストはありません。
フォントを描画して比較したり、アクセントを一律に除去したりするものではなく、
IDNAの完全な妥当性検査や、あらゆる見た目の偽装の検出も行いません。
通常のIDNクライアントはPunycodeのAラベルを送信します。
DNSラベルに直接入れられた任意のUTF-8文字列は、このフィルタの判定対象外です。

検査対象は問い合わせ名です。応答に含まれるすべてのCNAME先を独立に検査するものではありません。
別のリゾルバやDoHを使うクライアント、クライアント側にすでにキャッシュされた応答にも適用されません。

## 前提条件：本体での応答拒否への対応とchrootの解除

必要なUnbound本体の修正は、別プロジェクトの
[rioriost/unbound、コミット `17b4ab1b`](https://github.com/rioriost/unbound/commit/17b4ab1b72e1cc0e9569d51ccd7f352450bb9b04)
で管理しています。このコミット、または同等のディストリビューション向けバックポートを含む
ビルドを用意してください。フォークの既定ブランチに修正が含まれているとは限りません。
このリポジトリでは、別プロジェクトの本体を変更したり、同梱したりしていません。
ここで公開しているフィルタと導入用の資料だけでは、本体側の修正を代替できません。

ビルドと実行環境は、次の条件をすべて満たす必要があります。

- `unbound -V` の `Linked modules:` 行に `python` が含まれている。
- ビルドに対応する生成済みの `unboundmodule.py` を、組み込みPythonから読み込める。
  libunboundのPythonバインディングをインストールするだけでは不十分です。
- 組み込みPython APIに `INPLACE_REPLY_VETO_SUPPORTED = 1` があり、
  インプレース応答コールバックの失敗が実際にUnbound本体へ伝わる。
  マーカーだけがあっても不十分です。実リゾルバを使うテストで動作を確認します。
- テスト対象の `unbound` バイナリと同じディレクトリに `unbound-control` がある。
  テストでは本番の制御インターフェースを使わず、独立したUnix制御ソケットを使います。
- Python 3があり、リゾルバの非特権ユーザーで隔離された事前テストを実行できる。

未修正のUnbound 1.26.1と、調査したRHELの1.24.2ビルドは、インプレース応答コールバックの
失敗を無視します。Pythonフィルタが拒否しても、キャッシュから正の応答が返る場合があります。
また、Pythonの初期化処理で `False` を返すだけでは、起動を止められません。
このため、対応マーカーがない場合、データがない・壊れている場合、
コールバック登録に失敗した場合は、フィルタが**例外を送出して起動を停止します**。

PythonはUnboundがchrootに入った後に初期化されます。
この導入方法では、明示的に `chroot: ""` を指定する必要があります。
隔離の層を一つ外す変更になるため、許容できない環境では導入しないでください。
非特権のサービスアカウント、SELinux/AppArmor、ACLなど、他の保護は維持します。

セキュリティ修正をバックポートしているディストリビューションでは、
現在のベンダーソースパッケージに、本体の最小限の修正を加えて再ビルドしてください。
Pythonを有効にするためだけに、古い汎用の上流ソースアーカイブへ置き換えないでください。
現行のベンダーパッケージの再ビルドと動作確認は、運用者が行う必要があります。
[RHEL向けビルド手順](docs/rhel-build.md) に、ベンダーの修正を残した検証済みの手順と、
対象バージョン固有のパッケージ変更を記載しています。

## 既存のDNS設定を置き換えずに導入する

以下はLinux/systemd向けの例です。サービスのユーザーとグループは `unbound`、
バイナリの配置先は `/usr/sbin`、メイン設定は `/etc/unbound/unbound.conf` を前提とします。
ディストリビューションに合わせて、パスと名前を調整してください。
これは初回導入の手順であり、稼働中の環境を無人で更新するための手順ではありません。

独自ビルドのUnboundをインストールする前に、設定、サービスの上書き設定、
対応する元のパッケージをバックアップしてください。
ディストリビューションのパッケージ処理によって、リゾルバが再起動する場合があります。
フィルタを有効にする**前に**、対応済みのビルドと、それに一致するPythonラッパーを導入します。

```sh
python3 scripts/fetch_confusables.py
python3 -m unittest discover -s tests -v

sudo install -d -o root -g unbound -m 0755 /etc/unbound/homograph
sudo install -o root -g unbound -m 0644 \
    files/homograph_filter.py files/confusables.txt /etc/unbound/homograph/
sudo install -o root -g unbound -m 0644 \
    tests/test_homograph_integration.py /etc/unbound/homograph/selftest.py
```

`unbound-checkconf -o module-config /etc/unbound/unbound.conf` で現在のモジュール構成を確認します。
[`config/homograph.conf`](config/homograph.conf) のコピーを編集し、
**既存のモジュール列をすべて残したまま**、先頭に `python` を追加してください。
例えば `respip validator iterator` は `python respip validator iterator` にします。
既存のモジュールを削除したり、他のPython拡張の設定を上書きしたりしないでください。
調整した設定ファイルを配置します。

```sh
sudo install -o root -g unbound -m 0644 \
    config/homograph.conf /etc/unbound/homograph/homograph.conf
sudo restorecon -RF /etc/unbound/homograph  # SELinux systems only
```

この時点では、まだincludeを追加しません。既存のincludeやワイルドカード指定によって、
このディレクトリがすでに読み込まれる状態になっていないことも確認してください。
スクリプトとデータファイルは、サービスユーザーから書き込めない権限にします。
次回以降の更新では、別のバージョン付きディレクトリにファイルを配置し、
テストしてから設定を切り替えます。稼働中の配置先にあるファイルを上書きしただけで、
メモリ上のモジュールも再読み込みされたと判断しないでください。

## 有効化の前に実リゾルバで事前テストを行う

```sh
sudo -u unbound env \
    PYTHONDONTWRITEBYTECODE=1 \
    UNBOUND_BINARY=/usr/sbin/unbound \
    UNBOUND_FILTER_SCRIPT=/etc/unbound/homograph/homograph_filter.py \
    UNBOUND_CONFUSABLES=/etc/unbound/homograph/confusables.txt \
    python3 /etc/unbound/homograph/selftest.py -v
```

このテストは、非特権のループバックポートで、2スレッドの一時的なリゾルバと模擬上流を起動します。
53番ポートは使わず、稼働中のリゾルバを変更したり、外部へDNS問い合わせを送ったりしません。
事前に取得した正のキャッシュ応答を投入し、それがフィルタを通り抜けないことを確認します。
ローカル応答、許可する名前、不正なラベル、UDP/TCP、
A・AAAA・SVCB・HTTPS・MX・TXT・ANYも検査します。
データがない場合や壊れている場合は、実際に起動が失敗する必要があります。

未修正バイナリを使う追加テストは、`UNBOUND_UNPATCHED_BINARY` を指定した場合だけ実行されます。
そのバイナリに対応するラッパーを用意してください。未インストールのソースビルドでは、
`<binary-directory>/pythonmod/` が自動検出されます。
修正済みバイナリを未インストールのビルドから使う場合は、
生成された `pythonmod` ディレクトリを `PYTHONPATH` に設定します。
異なるビルドのラッパーを混在させないでください。

## 設定をアトミックに切り替えて有効化する

まず、代表的なローカルのA/AAAA、メール認証のTXT、PTR、外部の応答、
現在のDNSSECの動作を記録してください。
既存のlocal-data、広告遮断/RPZ、転送設定、待受、ACL、トラストアンカー、
systemdの上書き設定は維持します。
このフィルタは、DNSSEC検証の有効・無効を変更しません。

以下は、エラー時に停止するシェルで実行してください。
専用のincludeだけを追加し、メイン設定全体は再生成しません。
すでにPythonモジュールを有効にしている環境では別途統合が必要であり、
このままではモジュール列の一致確認で停止します。

```sh
set -eu
sudo install -d -m 0700 /var/lib/unbound-anti-homograph
backup=$(sudo mktemp -d /var/lib/unbound-anti-homograph/rollback.XXXXXXXX)
candidate=$(sudo mktemp /etc/unbound/.homograph.XXXXXXXX)
sudo cp --preserve=all /etc/unbound/unbound.conf "$backup/unbound.conf"
sudo cp --preserve=all /etc/unbound/unbound.conf "$candidate"
printf '\ninclude: "/etc/unbound/homograph/homograph.conf"\n' |
    sudo tee -a "$candidate" > /dev/null

old_modules=$(sudo unbound-checkconf -o module-config /etc/unbound/unbound.conf)
new_modules=$(sudo unbound-checkconf -o module-config "$candidate")
test "$new_modules" = "python $old_modules"
test -z "$(sudo unbound-checkconf -o chroot "$candidate")"
sudo unbound-checkconf "$candidate"
printf 'Rollback configuration: %s/unbound.conf\n' "$backup"

sudo mv "$candidate" /etc/unbound/unbound.conf
sudo restorecon /etc/unbound/unbound.conf  # SELinux systems only
sudo systemctl restart unbound
```

`unbound-checkconf` は、構文の確認だけでなくPythonの初期化も行います。
手順に沿った再起動の代わりにHUPやreloadを使わないでください。

`systemctl is-active` の結果だけでなく、実際のDNS応答を待ちます。
`Type=simple` のサービスは、応答できる状態になる前にactiveと表示される場合があります。
確認時間に上限を設けて問い合わせを再試行しても構いませんが、
知らせずにサービスをもう一度再起動してはいけません。

```sh
ready=false
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if response=$(dig @127.0.0.1 xn--mazon-3ve.com A +time=1 +tries=1 +noall +comments); then
        if printf '%s\n' "$response" | grep -q 'status: REFUSED'; then
            ready=true
            break
        fi
    fi
    sleep 1
done
test "$ready" = true
dig @127.0.0.1 xn--mazon-3ve.com AAAA +tcp +noall +comments
dig @127.0.0.1 amazon.com A +noall +comments +answer
```

拒否対象の名前は、UDPとTCPの両方で `REFUSED`、回答数ゼロになることを確認します。
正常な名前では、事前に記録したとおりの応答が返ることを確認してください。
LANクライアントからも確認し、IPv6を使っている環境ではIPv6経由でも確認します。
ジャーナルとSELinux/AppArmorなどの強制アクセス制御による拒否ログを調べ、
既存レコードの応答を変更前と比較してください。

通常の問い合わせと、キャッシュ応答を破棄した後の問い合わせには、`REFUSED`（rcode 5）を返します。
local-dataから正の応答が返る経路では、応答コールバックの失敗を処理するため、
`SERVFAIL`（rcode 2）になります。どちらの経路でも正の応答は返しません。
拒否理由は `homograph:` で始まるログに記録し、共有キャッシュの応答オブジェクト自体は変更しません。

## ロールバックは明示的に行う

確認に失敗したら反映作業を中止し、失敗を報告してください。
SELinuxを無効にしたり、エラーを無視したりしてはいけません。
保存したメイン設定を元の設定と同じディレクトリの一時ファイルに復元し、
検証してから稼働中の設定とアトミックに置き換えます。
セキュリティコンテキストを復元し、復旧のための再起動を明示的に行ってください。
その後、元の正常な名前解決が戻ったことを確認します。

フィルタ導入前のメイン設定に戻すと、includeが外れ、元のchrootとモジュール構成に戻ります。
正しく修正されたバイナリを残したまま、このポリシーだけを無効にしても問題ありません。
パッケージも戻す場合は、先にポリシーを外し、その後で、対応の取れたバイナリ、
ラッパー、ライブラリ、関連パッケージを復元します。
未対応のバイナリに戻した状態で、フィルタを有効のままにしないでください。

復旧用のバックアップには運用設定が含まれます。rootだけがアクセスできる状態で保管し、
インベントリ、ログ、ホスト名、鍵、本番のレコードとともに、このリポジトリへアップロードしないでください。

## 更新とライセンス

対応状況の検査は残し、Unboundを更新するたびに、実リゾルバを使う事前テストを実行してください。
将来の標準パッケージが独自ビルドを置き換えた場合、検査によって起動が停止します。
フィルタをすり抜けたまま稼働を続けることはありません。
ベンダーの新しいセキュリティ更新に合わせて再ビルドを計画し、
DNSの可用性と、ポリシーによる拒否の両方を監視してください。
古いセキュリティ修正版に固定し続けないでください。

Unicodeデータを更新する場合は、URLとチェックサムを同時に変更します。
対応付けの変更と、正当な名前を誤って拒否する影響を確認し、
有効化する前にすべてのテストを再実行してください。

本プロジェクト独自のコード、テスト、設定例、ドキュメントは **MITライセンス**です。
依存先のUnboundはBSD-3-Clauseのままで、Unicodeデータにも固有のライセンスが適用されます。
詳しくは [NOTICE](NOTICE) を参照してください。
