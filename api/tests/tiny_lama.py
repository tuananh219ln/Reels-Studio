"""A stand-in for the LaMa ONNX model with the real one's inputs and output: `image` (1x3x512x512, 0–1) and `mask`
(1x1x512x512, 1 where to fill) in, `output` (1x3x512x512, 0–255) out. It paints the hole FILL and returns the rest
as it came, so a test sees which pixels went through it, without the real 200 MB model."""

from pathlib import Path

import onnx
from onnx import TensorProto, helper

FILL = 128


def write(path: Path) -> Path:
    side = 512
    nodes = [
        helper.make_node("Sub", ["one", "mask"], ["kept"]),
        helper.make_node("Mul", ["image", "kept"], ["image_kept"]),
        helper.make_node("Mul", ["image_kept", "scale"], ["image_255"]),
        helper.make_node("Mul", ["mask", "fill"], ["hole"]),
        helper.make_node("Add", ["image_255", "hole"], ["output"]),
    ]
    graph = helper.make_graph(
        nodes,
        "tiny_lama",
        [
            helper.make_tensor_value_info("image", TensorProto.FLOAT, ["batch", 3, side, side]),
            helper.make_tensor_value_info("mask", TensorProto.FLOAT, ["batch", 1, side, side]),
        ],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, ["batch", 3, side, side])],
        [
            helper.make_tensor("one", TensorProto.FLOAT, [], [1.0]),
            helper.make_tensor("scale", TensorProto.FLOAT, [], [255.0]),
            helper.make_tensor("fill", TensorProto.FLOAT, [], [float(FILL)]),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return path
