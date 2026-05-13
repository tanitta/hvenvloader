# Houdini venv Loader (hvenvloader)

[English](README.md) | [日本語](README.ja.md)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/tanitta/hvenvloader/blob/main/LICENSE)

## 概要

hvenvloader は、Python プロジェクトのワークフローで Houdini を使うための Houdini Package です。主に次の機能を提供します。

- プロジェクトローカルの Python 仮想環境 `.venv` に入っている Python package を Houdini から読み込む。
- `.venv` に Python package としてインストールされた Native venvloader Houdini Package (NVHP) を読み込む。
- プロジェクトの `.venv` を使って Houdini を起動する launcher (`houdini.bat` または `houdini.sh`) を作成する。
- uv プロジェクトの初期化、NVHP の作成、よく使う uv 操作のための shelf tool を提供する。

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
- `venv > Create NVHP` は、NVHP JSON と標準的な Houdini asset directory を含む Python package を作成する dialog を開きます。
- `venv > Export NVHP` は、NVHP package directory を通常の Houdini Package layout に書き出す dialog を開きます。
- `venv > uv` は、`uv init`、`uv sync`、`uv add`、`uv remove`、`uv lock`、`uv tree`、launcher 生成を行うための簡単な UI を開きます。local package の追加と `uv add --editable` にも対応しています。

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
2. `PYTHONPATH` を `.venv` の `site-packages` directory に設定します。
3. `HOUDINI_PACKAGE_DIR` を `.venv` の `site-packages` directory に設定し、必要な場合は生成済み editable package directory も追加します。
4. インストール済み Python package 内の `hpackage.json` を Houdini package search directory へ同期し、Houdini が discovery できるようにします。editable local install では元の JSON 内容を保持し、生成済みの静的 overlay と source package directory への directory link を使います。
5. `HVENVLOADER_LAUNCHER=1` を設定し、launcher を使わない場合の fallback が実行されないようにします。
6. project の virtual environment を利用できる状態で Houdini を起動します。

shelf tool を使わない場合は、適切な launcher (`houdini.bat` または `houdini.sh`) を project root に手動でコピーし、自分の環境に合わせて Houdini executable path と `HOUDINI_USER_PREF_DIR` の値を編集してください。

## Launcher を使わない場合の挙動

生成された launcher を使わずに Houdini を起動した場合、hvenvloader は `python3.11libs/ready.py` に fallback します。

この mode では、hvenvloader は `$JOB/.venv` の `site-packages` を Houdini の Python path に追加するだけです。インストール済み Python package に含まれる NVHP file は、launcher を使わない fallback mode では読み込まれません。`.venv` から NVHP も discovery したい場合は、生成された launcher を使用してください。

## 使い方

1. Python package を project の `.venv` にインストールします。
2. `.venv` 内の Python package と NVHP の両方が必要な場合は、project root の launcher から Houdini を起動します。
3. project の `.hip` file を開きます。

通常の Houdini shortcut から起動した場合でも、`ready.py` fallback により `$JOB/.venv` にインストールされた Python package は利用できます。ただし、それらの package が提供する NVHP file は読み込まれません。

## Native venvloader Houdini Package (NVHP) の作成

hvenvloader は、project の `.venv` にインストールされた Python package 内に配布されている NVHP `.json` file を読み込めます。実用例として [HoudiniUnityAnimationClip](https://github.com/tanitta/HoudiniUnityAnimationClip) を参照してください。

最も簡単な始め方は、Houdini で `venv > Create NVHP` を実行することです。この shelf tool は dialog を開き、保存場所、project name、import package name、Houdini environment variable name、Python requirement、作成する標準 Houdini directory を指定できます。実行すると、Python package layout、`pyproject.toml`、`hpackage.json` が作成されます。

NVHP は意図的に hvenvloader 専用の format です。単体で通常の Houdini Package として導入できる source layout ではありません。Python import package root を Houdini package root として扱うため、`__init__.py` と `hpackage.json` は `src/<package>/` の直下に並びます。Python code は Houdini の `scripts/python` convention ではなく、通常の Python package として import します。

重要な convention は、NVHP を提供する各 Python import package が `hpackage.json` という file を含むことです。launcher は `.venv` の metadata と package directory を scan し、`<package>/hpackage.json` を見つけると、その JSON を `HOUDINI_PACKAGE_DIR` 経由で Houdini が discovery できるようにします。

通常 install では import package が `site-packages` 配下に配置されるため、launcher は `hpackage.json` を `site-packages/<package>.json` に直接コピーします。editable local install では import package が source checkout 側に残るため、launcher は `.dist-info/direct_url.json` と `top_level.txt` を読み、`.venv/.../site-packages/_hvenvloader_houdini_packages/` を起動時に作り直し、そこに `hpackage.json` を内容未変更でコピーし、source package directory を指す `<package>` という生成済み directory link を作成します。launcher はその生成済み directory を `HOUDINI_PACKAGE_DIR` に直接追加します。

NVHP はこの `.venv` layout に依存するため、uv で install し、生成された hvenvloader launcher から Houdini を起動してください。source checkout を通常の Houdini Package として直接導入する使い方はサポートしません。この割り切りにより、Houdini、`uv run`、test、build script の間で import の挙動を揃えます。

通常の Houdini Package として配布したい場合は、`venv > Export NVHP` を使います。exporter は `src/MyHoudiniPackage/` のような NVHP package directory と export directory を受け取り、次の layout を書き出します。

```text
export/
  MyHoudiniPackage.json
  MyHoudiniPackage/
    otls/
    toolbar/
    scripts/
      python/
        MyHoudiniPackage/
          __init__.py
```

export される top-level JSON は `hpackage.json` を内容未変更でコピーします。Python source file (`*.py`) は directory structure を保ったまま Houdini の `scripts/python/<package>/` にコピーします。module tree 内の non-Python file はそこにはコピーしません。Houdini asset directory は exported package folder の直下に残します。`otls`、`scripts`、`toolbar`、`python_panels`、`usd` など、Houdini asset directory として予約されている top-level 名は Houdini asset directory として扱います。NVHP の Python subpackage にはそれらの名前を使わないでください。

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

shelf tool を使わない場合は、この構成を手動で作成することもできます。

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

NVHP JSON と Houdini asset を Python package data として含めてください。setuptools を使う最小構成の `pyproject.toml` は次のようになります。

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "MyHoudiniPackage"
version = "0.1.0"
description = "My native venvloader Houdini package."
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

その後、生成された project launcher (`houdini.bat` または `houdini.sh`) から Houdini を再起動します。起動時に hvenvloader は Python package を import 可能にし、`hpackage.json` を Houdini package search directory から `MyHoudiniPackage.json` として見えるようにします。
