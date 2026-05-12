# Houdini venv Loader (hvenvloader)

[English](README.md) | [日本語](README.ja.md)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/tanitta/hvenvloader/blob/main/LICENSE)

## 概要

hvenvloader は、Python プロジェクトのワークフローで Houdini を使うための Houdini Package です。主に次の機能を提供します。

- プロジェクトローカルの Python 仮想環境 `.venv` に入っている Python package を Houdini から読み込む。
- `.venv` にインストールされた Python package に含まれる [Houdini Package](https://www.sidefx.com/docs/houdini/ref/plugins.html) ファイルを読み込む。
- プロジェクトの `.venv` を使って Houdini を起動する launcher (`houdini.bat` または `houdini.sh`) を作成する。
- uv プロジェクトの初期化、hvenvloader 互換 Houdini package の作成、よく使う uv 操作のための shelf tool を提供する。

## インストール

1. [uv](https://docs.astral.sh/uv/) をインストールし、Houdini から `uv` コマンドを実行できるようにします。
2. このリポジトリを `$HOUDINI_USER_PREF_DIR/packages/hvenvloader` に clone します。
3. `hvenvloader.json` を `$HOUDINI_USER_PREF_DIR/packages/hvenvloader.json` にコピーします。
4. Houdini を再起動します。

`hvenvloader.json` は、この package を Houdini に登録するためのファイルです。詳細は [Houdini packages | Houdini help](https://www.sidefx.com/docs/houdini/ref/plugins.html) も参照してください。

## プロジェクト設定

1. Houdini project を作成または開き、`$JOB` を project root directory に設定します。
2. `venv > Init Project` shelf tool を実行します。
3. shelf tool は `$JOB` で `uv init` と `uv sync` を実行して `.venv` を作成し、project root に launcher を書き込みます。
   - Windows では `houdini.bat`
   - それ以外の platform では `houdini.sh`
4. Houdini を閉じます。
5. 通常の Houdini shortcut ではなく、project root に生成された launcher から Houdini を起動します。

生成された launcher は project の一部です。project の `.venv` と同じ場所に置いたまま、その project で作業するときに使用してください。

## Shelf Tools

- `venv > Init Project` は `uv init`、`uv sync` を実行し、project launcher を書き込みます。
- `venv > Create Houdini Package` は、Houdini Package JSON と標準的な Houdini asset directory を含む Python package を作成する dialog を開きます。
- `venv > uv` は、`uv init`、`uv sync`、`uv add`、`uv remove`、`uv lock`、`uv tree`、launcher 生成を行うための簡単な UI を開きます。

## Launcher の挙動

`houdini.bat` と `houdini.sh` は project root 用の launcher です。次のような directory layout を想定しています。

```text
project-root/
  .venv/
  houdini.bat or houdini.sh
  your_project.hip
```

launcher から Houdini を起動すると、次の処理を行います。

1. launcher file からの相対位置で project の `.venv` を探します。
2. `HOUDINI_PACKAGE_DIR` と `PYTHONPATH` を `.venv` の `site-packages` directory に設定します。
3. インストール済み Python package 内の `hpackage.json` を `site-packages` 直下へ Houdini package `.json` としてコピーし、Houdini が discovery できるようにします。
4. `HVENVLOADER_LAUNCHER=1` を設定し、`456.py` fallback が実行されないようにします。
5. project の virtual environment を利用できる状態で Houdini を起動します。

shelf tool を使わない場合は、適切な launcher (`houdini.bat` または `houdini.sh`) を project root に手動でコピーし、自分の環境に合わせて Houdini executable path と `HOUDINI_USER_PREF_DIR` の値を編集してください。

## Launcher を使わない場合の挙動

生成された launcher を使わずに Houdini を起動した場合、hvenvloader は `scripts/456.py` に fallback します。

この mode では、hvenvloader は `$JOB/.venv` の `site-packages` を Houdini の Python path に追加するだけです。インストール済み Python package に含まれる Houdini Package file は、`456.py` mode では読み込まれません。`.venv` から Houdini Package も discovery したい場合は、生成された launcher を使用してください。

## 使い方

1. Python package を project の `.venv` にインストールします。
2. `.venv` 内の Python package と Houdini Package の両方が必要な場合は、project root の launcher から Houdini を起動します。
3. project の `.hip` file を開きます。

通常の Houdini shortcut から起動した場合でも、`456.py` fallback により `$JOB/.venv` にインストールされた Python package は利用できます。ただし、それらの package が提供する Houdini Package file は読み込まれません。

## hvenvloader 互換 Houdini Package の作成

hvenvloader は、project の `.venv` にインストールされた Python package 内に配布されている Houdini Package `.json` file を読み込めます。実用例として [HoudiniUnityAnimationClip](https://github.com/tanitta/HoudiniUnityAnimationClip) を参照してください。

重要な convention は、Houdini Package を提供する各 Python import package が `hpackage.json` という file を含むことです。launcher は `.venv` の `site-packages` 内の各 directory を scan し、`<package>/hpackage.json` を見つけると、その JSON file を `site-packages` 直下に `<package>.json` としてコピーします。これにより Houdini は `HOUDINI_PACKAGE_DIR` 経由で package を discovery できます。

次の layout を starting point として使えます。

```text
my-houdini-package/
  pyproject.toml
  README.md
  src/
    MyHoudiniPackage/
      __init__.py
      hpackage.json
      otls/
        my_asset.hda
```

この構成は Houdini から `venv > Create Houdini Package` で作成できます。

`hpackage.json` は、インストールされた Python package directory を Houdini に指し示す必要があります。例:

```json
{
  "hpath": "$MYHOUDINIPACKAGE",
  "env": [
    {
      "MYHOUDINIPACKAGE": "$HOUDINI_PACKAGE_PATH/MyHoudiniPackage"
    }
  ]
}
```

この package file により、Houdini はインストール済み package directory を Houdini path として解決できます。そのため、`otls`、`scripts`、`toolbar`、`python_panels` などの標準的な Houdini subdirectory を `src/MyHoudiniPackage/` の下に置けます。

Houdini Package JSON と Houdini asset を Python package data として含めてください。setuptools を使う最小構成の `pyproject.toml` は次のようになります。

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "MyHoudiniPackage"
version = "0.1.0"
description = "My hvenvloader-compatible Houdini package."
requires-python = ">=3.10"
dependencies = []

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
MyHoudiniPackage = [
  "hpackage.json",
  "otls/**/*",
  "scripts/**/*",
  "toolbar/**/*",
  "python_panels/**/*",
]
```

package を publish した後、または Git repository から利用できるようにした後、project root で Houdini project に追加します。

```shell
uv add "MyHoudiniPackage @ git+https://github.com/owner/MyHoudiniPackage.git"
uv sync
```

その後、生成された project launcher (`houdini.bat` または `houdini.sh`) から Houdini を再起動します。起動時に hvenvloader は Python package を import 可能にし、`hpackage.json` を package search directory に `MyHoudiniPackage.json` としてコピーします。
