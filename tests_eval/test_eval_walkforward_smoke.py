import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.eval_walkforward import run_walkforward

def test_run_walkforward_outputs():
    res = run_walkforward(n_folds=4)
    assert "oos" in res and "overall_auc" in res and "auc_ci" in res
    oos = res["oos"]
    for col in ["date", "label", "forward_return", "proba", "fold_id", "fold_threshold"]:
        assert col in oos.columns, f"缺列 {col}"
    assert oos["proba"].between(0, 1).all()
    assert 0.0 <= res["overall_auc"] <= 1.0
    lo, hi = res["auc_ci"]
    assert lo <= res["overall_auc"] <= hi
    assert os.path.exists(res["oos_csv_path"])
    print("OK", "overall_auc=%.3f CI=(%.3f,%.3f) n=%d" %
          (res["overall_auc"], lo, hi, len(oos)))

if __name__ == "__main__":
    test_run_walkforward_outputs()
