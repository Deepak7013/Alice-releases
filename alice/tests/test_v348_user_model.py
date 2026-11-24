from pathlib import Path
from alice.user_model import UserModel
from alice.learning import LearningStore

def test_user_model_loads_persisted_facts(tmp_path):
    p=tmp_path/'user.json'; a=UserModel(p); a.learn('style','concise',verified=True)
    b=UserModel(p); assert b.get('style',verified_only=True).value=='concise'

def test_user_model_unverified_is_not_verified_context(tmp_path):
    p=tmp_path/'user.json'; a=UserModel(p); a.learn('rule','pending')
    assert a.get('rule',verified_only=True) is None
    assert a.context('pending')==''

def test_learning_store_loads_on_startup(tmp_path):
    p=tmp_path/'lessons.json'; a=LearningStore(p); a.learn('regression','always retain',verified=True)
    b=LearningStore(p); assert b.get('regression',verified_only=True).value=='always retain'
