from alice.engineering.regression import RegressionBaseline
def test_regression_fingerprint_detects_change(tmp_path):
 (tmp_path/"a.py").write_text("x=1\n",encoding="utf-8"); b=RegressionBaseline(tmp_path); fp=b.fingerprint(); assert b.matches(fp)
 (tmp_path/"a.py").write_text("x=2\n",encoding="utf-8"); assert not b.matches(fp)
