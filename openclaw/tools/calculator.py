"""Safe math evaluation using Python AST."""

import ast
import math
import operator

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}

_SAFE_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}


def _eval_node(node: ast.AST) -> float:
    """Safely evaluate an AST node."""
    if isinstance(node, ast.Constant):
        return float(node.value)

    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.operand))

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in _SAFE_NAMES:
            args = [_eval_node(a) for a in node.args]
            return _SAFE_NAMES[node.func.id](*args)

    raise ValueError(f"Unsafe expression: {ast.dump(node)}")


def calculate(expression: str) -> str:
    """Safely evaluate a math expression. Returns result string or error."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree.body)
        # Clean up float presentation
        if result == int(result):
            return str(int(result))
        return f"{result:.6g}"
    except Exception as e:
        return f"[calculator error: {e}]"
