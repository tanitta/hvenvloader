from pathlib import Path

import hou


OUTPUT_PATH = Path(__file__).with_name("networkx_node_graph.hip")


def create_example_scene():
    hou.hipFile.clear(suppress_save_prompt=True)

    object_context = hou.node("/obj")
    geometry = object_context.createNode(
        "geo",
        node_name="networkx_example",
        run_init_scripts=False,
    )

    box = geometry.createNode("box", node_name="box1")
    transform = geometry.createNode("xform", node_name="transform1")
    output = geometry.createNode("null", node_name="OUT")
    sphere = geometry.createNode("sphere", node_name="sphere1")

    transform.setInput(0, box)
    output.setInput(0, transform)
    output.setDisplayFlag(True)
    output.setRenderFlag(True)

    box.setPosition(hou.Vector2(0, 2))
    transform.setPosition(hou.Vector2(0, 1))
    output.setPosition(hou.Vector2(0, 0))
    sphere.setPosition(hou.Vector2(3, 2))

    geometry.setCurrent(True, clear_all_selected=True)
    hou.hipFile.save(file_name=str(OUTPUT_PATH))


if __name__ == "__main__":
    create_example_scene()
    print("Wrote {}".format(OUTPUT_PATH))
