from alice.intelligence.algorithms import AlgorithmAdvisor, AlgorithmExecutor, AlgorithmCatalog

def test_algorithm_advisor_prefers_explainable_local_retrieval():
    a=AlgorithmAdvisor().recommend("retrieve from a small local corpus",data={"size":100,"requires_explainability":True},top_k=3)
    assert a[0]["algorithm"]=="tfidf_cosine"

def test_algorithm_executor_guards_cycle():
    try: AlgorithmExecutor.topological_order(["a","b"],[("a","b"),("b","a")])
    except ValueError: pass
    else: assert False

def test_planning_chooses_dependency_algorithm():
    x=AlgorithmAdvisor().recommend("plan tasks with dependencies",top_k=5)
    assert any(i["algorithm"]=="topological_sort" for i in x)

def test_clustering_outlier_data_prefers_dbscan():
    x=AlgorithmAdvisor().recommend("cluster unknown groups with outliers",data={"outliers":True,"unknown_k":True},top_k=5)
    assert x[0]["algorithm"]=="dbscan"

def test_algorithm_catalog_has_core_families():
    fam={x["family"] for x in AlgorithmCatalog().list()}
    assert {"retrieval","ranking","clustering","planning","scheduling","optimization","anomaly"} <= fam
