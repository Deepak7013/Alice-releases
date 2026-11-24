from alice.health import HealthDiagnostics
from alice.memory_context import ContextMemory, ContextRetriever, MemoryItem, MemoryKind, MemoryScope
from alice.integrations import IntegrationRegistry, IntegrationStatus
from alice.conversation import ConversationContext

def test_public_memory_exports():
    assert ContextMemory and ContextRetriever and MemoryItem and MemoryKind and MemoryScope

def test_health_imports():
    r=HealthDiagnostics().run(); assert r.ok

def test_contracts_and_context():
    reg=IntegrationRegistry(); reg.register(IntegrationStatus('browser',True,False,['read']))
    assert reg.get('browser').available
    c=ConversationContext(); c.add('user','build a bike site'); c.set('project','bike-store'); assert c.recent(1)[0]['content']=='build a bike site'
