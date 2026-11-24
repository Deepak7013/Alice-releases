from alice.knowledge.graph import KnowledgeGraph
def test_graph_links_and_neighbors(tmp_path):
 g=KnowledgeGraph(tmp_path); a=g.node('Project',kind='project'); b=g.node('Task',kind='task'); g.link(a,'contains',b); assert g.related(a,b); assert g.neighbors(a)[0]['id']==b
def test_graph_unknown_node(tmp_path):
 g=KnowledgeGraph(tmp_path); a=g.node('A')
 try: g.link(a,'x','missing'); assert False
 except KeyError: pass
