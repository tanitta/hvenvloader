# hvenvloader で NetworkX を Houdini から使う

このチュートリアルでは、Houdini に標準搭載されていない Python package の例として [NetworkX](https://networkx.org/) を project の `.venv` に追加し、Houdini の node network を解析します。同じ directory に、すぐ試せる [`networkx_node_graph.hip`](networkx_node_graph.hip) も用意しています。

完成すると、次のことができるようになります。

- Python package を Houdini 本体の install directory へ追加せず、project ごとに管理する。
- Houdini から project の `.venv` にある package を import する。
- Houdini node の接続を NetworkX の有向 graph に変換する。
- node を依存関係の level ごとに一覧表示する。

この例では Pure Python package である NetworkX を使うため、native library や platform 固有の binary compatibility を意識せずに hvenvloader の基本的な流れを確認できます。

## 前提条件

作業を始める前に、次を用意してください。

- hvenvloader が Houdini に install されている。
- `uv` command を実行できる。
- Houdini project 用の directory があり、その場所を `$JOB` に設定している。

以下では、この directory を `<project-root>` と表記します。

## 1. Project と launcher を作成する

Houdini の shelf から `venv > Init Project` を実行します。

1. **Project Root** が目的の project directory になっていることを確認します。
2. `uv init`、`uv sync`、`Write launcher` を有効にします。
3. **Run Selected** を押します。

初期設定のまま実行した場合、project は install 可能な Python package として初期化されます。このチュートリアルでは project 自体の Python module は使用しませんが、そのままで問題ありません。

処理が完了すると、主に次の file と directory が作成されます。

```text
<project-root>/
  .venv/
  pyproject.toml
  uv.lock
  houdini.bat     # Windows
  houdini.sh      # Linux / macOS
```

launcher の project root は `$JOB` からではなく、launcher 自身が置かれている directory から決まります。

## 2. NetworkX を `.venv` に追加する

Houdini の shelf から `venv > uv` を実行します。

1. **Project Root** に `<project-root>` を指定します。
2. **Package** に `networkx` と入力します。
3. **Install as editable (--editable)** はオフのままにします。
4. **Install package (uv add)** を押します。
5. 出力欄の最後が `exit code: 0` になったことを確認します。

terminal から操作する場合は、同じ project root で次を実行しても構いません。

```console
cd <project-root>
uv add networkx
```

`uv add` は NetworkX を `.venv` に install し、依存関係を `pyproject.toml` と `uv.lock` に記録します。Houdini 本体の Python environment は変更しません。

## 3. Project launcher から Houdini を起動する

いったん Houdini を終了し、生成された launcher から起動し直します。

Windows:

```text
<project-root>/houdini.bat
```

Linux / macOS:

```console
cd <project-root>
./houdini.sh
```

通常の Houdini shortcut ではなく、この project の launcher を使用してください。launcher は自身の directory にある `.venv` の `site-packages` を Houdini の Python path に追加します。

## 4. Import 元を確認する

Houdini の Python Shell または Python Source Editor で次を実行します。

```python
from pathlib import Path

import networkx as nx

print("NetworkX version:", nx.__version__)
print("Loaded from:", Path(nx.__file__).resolve())
```

`Loaded from` が次のように project の `.venv` 配下を指していれば成功です。

Windows の例:

```text
C:\projects\my-houdini-project\.venv\Lib\site-packages\networkx\__init__.py
```

Linux / macOS の例:

```text
/projects/my-houdini-project/.venv/lib/python3.11/site-packages/networkx/__init__.py
```

Houdini の `sys.executable` 自体が `.venv` の Python に変わるわけではありません。Houdini の Python interpreter はそのままに、project-local な `site-packages` を import path へ追加するのが hvenvloader の役割です。

## 5. Example scene を開く

この README と同じ directory にある `networkx_node_graph.hip` を `<project-root>` へコピーし、launcher から起動した Houdini で開きます。

```text
Examples/networkx/networkx_node_graph.hip
  -> <project-root>/networkx_node_graph.hip
```

`/obj/networkx_example` の中には、次の node graph が入っています。

```text
box1 -> transform1 -> OUT

sphere1
```

`sphere1` はほかの node に接続されていません。このため、NetworkX で依存関係を分類すると `box1` と `sphere1` が同じ最初の level に入ります。

## 6. Houdini node network を解析する

`/obj/networkx_example` 内の node を1つ選択してから、Python Shell または Python Source Editor で次の code を実行します。

```python
import hou
import networkx as nx


selected_nodes = hou.selectedNodes()
if not selected_nodes:
    raise hou.Error("解析する network 内の node を1つ選択してください。")

parent = selected_nodes[0].parent()
network_nodes = tuple(parent.children())
network_node_set = set(network_nodes)

graph = nx.DiGraph()

for node in network_nodes:
    graph.add_node(node.path())

    for input_node in node.inputs():
        if input_node is not None and input_node in network_node_set:
            graph.add_edge(input_node.path(), node.path())

print("Network:", parent.path())
print("Nodes:", graph.number_of_nodes())
print("Connections:", graph.number_of_edges())

if nx.is_directed_acyclic_graph(graph):
    print("Dependency levels:")

    for level, paths in enumerate(nx.topological_generations(graph)):
        names = [hou.node(path).name() for path in paths]
        print("  Level {}: {}".format(level, ", ".join(names)))
else:
    print("Cycles:")

    for cycle in nx.simple_cycles(graph):
        print("  " + " -> ".join(cycle))
```

例えば `box1 -> transform1 -> OUT` という接続と、未接続の `sphere1` がある場合、次のような結果になります。

```text
Network: /obj/geo1
Nodes: 4
Connections: 2
Dependency levels:
  Level 0: box1, sphere1
  Level 1: transform1
  Level 2: OUT
```

`topological_generations()` は、先行 node に依存しない node を Level 0、その結果を必要とする node を Level 1 以降として分類します。この graph を発展させると、network validation、命名規則の検査、依存関係の可視化などにも利用できます。

## 7. NetworkX を削除する

不要になった場合は `venv > uv` を開き、**Package** に `networkx` と入力して **Remove package (uv remove)** を押します。

terminal から削除する場合は次を実行します。

```console
cd <project-root>
uv remove networkx
```

すでに `import networkx` を実行した Houdini process では module が memory に残っています。削除結果を確認するときは Houdini を終了し、project launcher から起動し直してください。

## Troubleshooting

### `ModuleNotFoundError: No module named 'networkx'`

次を順番に確認します。

1. `venv > uv` の **Project Root** と launcher の directory が同じか。
2. `uv add networkx` が `exit code: 0` で終了したか。
3. `<project-root>/.venv` が存在するか。
4. 通常の shortcut ではなく `<project-root>` の launcher から Houdini を起動したか。
5. hvenvloader の更新後に、project launcher を再生成したか。

Houdini から次を実行すると、現在の import path を確認できます。

```python
import sys

print("\n".join(sys.path))
```

project の `.venv` にある `site-packages` が一覧に含まれていることを確認してください。

### 別の package でも同じ方法を使えるか

Pure Python package は同じ手順で利用できます。native extension を含む package の場合は、Houdini が使用する Python の minor version、operating system、CPU architecture と互換性のある wheel が必要です。

package は Houdini の install directory に直接 `pip install` せず、project の `pyproject.toml` と `uv.lock` で管理してください。

## Example scene を再生成する

repository の保守時に `.hip` を再生成する場合は、同じ directory の `generate_hip.py` を `hython` で実行します。

```console
hython Examples/networkx/generate_hip.py
```

この script は `networkx_node_graph.hip` を上書きします。通常のチュートリアル利用時に実行する必要はありません。
