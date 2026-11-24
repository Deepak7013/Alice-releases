from alice.user_model import UserModel
from alice.learning import LearningStore
from alice.cognitive.context import KnowledgeContextBuilder
from alice.world.model import WorldModel

def test_context_bridge_only_uses_verified_knowledge(tmp_path):
    u=UserModel(tmp_path/'u.json'); l=LearningStore(tmp_path/'l.json')
    u.learn('preference','short answers',verified=False); l.learn('rule','regressions persist',verified=True)
    c=KnowledgeContextBuilder(u,l).build('rule')
    assert not c.user_facts and c.lessons and 'learning:verified' in c.sources

def test_context_bridge_has_no_execution_authority(tmp_path):
    c=KnowledgeContextBuilder(UserModel(tmp_path/'u.json'),LearningStore(tmp_path/'l.json')).build('open app')
    assert not hasattr(c,'execute') and not hasattr(c,'approval')

def test_world_context_bridge_is_bounded_and_fails_open_for_planning_when_observer_errors(tmp_path):
    class World:
        def planning_summary(self,request,max_chars=0):
            assert request=="connect to phone"
            assert max_chars==1200
            return '{"freshness":{"android":{"fresh":false}}}'
    ctx=KnowledgeContextBuilder(world_model=World()).build("connect to phone")
    assert ctx.world["trust"]=="observation_only"
    assert '"fresh":false' in ctx.world["context"]
    assert ctx.world["policy"]=="metadata_only; values and identifiers omitted"
    assert "world_model:observations" in ctx.sources

    class Broken:
        def planning_summary(self,**_kwargs): raise RuntimeError("observer unavailable")
    fallback=KnowledgeContextBuilder(world_model=Broken()).build("connect to phone")
    assert fallback.world=={}
    assert "world_model:observations" not in fallback.sources


def test_world_context_bridge_never_falls_back_to_raw_values_or_entity_ids(tmp_path):
    class RawOnlyWorld:
        def context(self,**_kwargs):
            raise AssertionError("raw observations must not be read for planning context")

    assert KnowledgeContextBuilder(world_model=RawOnlyWorld()).build("open browser").world == {}

    world=WorldModel(tmp_path)
    world.update("browser",{"url":"https://private.example/path?token=SECRET_VALUE"},
                 source="browser",ttl_seconds=60)
    world.set_entity("browser","DEVICE-PRIVATE-987",{"title":"PRIVATE_WINDOW"},source="uia")
    result=KnowledgeContextBuilder(world_model=world).build("open browser")
    serialized=str(result.world)
    assert '"domain":"browser"' in serialized
    assert "private.example" not in serialized
    assert "SECRET_VALUE" not in serialized
    assert "DEVICE-PRIVATE-987" not in serialized
    assert "PRIVATE_WINDOW" not in serialized
