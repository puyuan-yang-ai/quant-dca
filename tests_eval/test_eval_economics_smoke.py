import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.eval_economics import run_economics

def test_run_economics_outputs():
    res = run_economics()
    for k in ["engine_A", "engine_B_foldinternal", "engine_B_05",
              "conditional", "sweep"]:
        assert k in res, f"缺 {k}"
    for grp in ["engine_A", "engine_B_foldinternal", "engine_B_05"]:
        for m in ["sharpe_ratio", "max_drawdown", "total_return"]:
            assert m in res[grp], f"{grp} 缺 {m}"
    c = res["conditional"]
    for m in ["e_pass", "e_skip", "e_all", "expectancy", "t_stat", "t_p"]:
        assert m in c
    assert len(res["sweep"]) >= 5  # 阈值曲线点数
    print("OK A_sharpe=%.3f Bfi_sharpe=%.3f" %
          (res["engine_A"]["sharpe_ratio"], res["engine_B_foldinternal"]["sharpe_ratio"]))

if __name__ == "__main__":
    test_run_economics_outputs()
