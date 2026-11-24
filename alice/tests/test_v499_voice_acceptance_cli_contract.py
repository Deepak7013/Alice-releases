import ast
from pathlib import Path


def test_voice_acceptance_cli_uses_report_function_keyword_contract():
    source = Path(__file__).resolve().parents[2] / "ALICE_VOICE_ACCEPTANCE_CHECK.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    report_function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "summarize_voice_diagnostics"
    )
    accepted = {arg.arg for arg in report_function.args.kwonlyargs}
    call = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "summarize_voice_diagnostics"
        and any(keyword.arg == "piper_status" for keyword in node.keywords)
    )
    supplied = {keyword.arg for keyword in call.keywords}
    assert supplied <= accepted
    assert {"piper_status", "neural_status"} <= supplied
    assert "piper" not in supplied
    assert "neural" not in supplied
