from pathlib import Path

def test_final_goal_contract_is_present():
    root=Path(__file__).resolve().parents[2]
    text=(root/'ALICE_FINAL_GOAL.md').read_text(encoding='utf-8').lower()
    assert 'persistent personal executive intelligence' in text
    assert 'external ai models are optional accelerators' in text
    assert 'understand -> retrieve -> inspect -> plan -> authorize -> act' in text
    assert 'self-engineering' in text
