"""
ML Meta-Labeling MVP — 一键运行入口

使用方式:
    cd /home/puyuyang/Projects/quant-dca
    python -m ml.run_mvp                          # 使用 versions.py 中激活版本
    python -m ml.run_mvp --method sl_proximity    # 指定标注方法
    python -m ml.run_mvp --method all             # 四种全跑，横向对比
"""
import argparse
import importlib
from ml.labeling import run as run_labeling, load_spy
from ml.evaluate import train_and_evaluate
from ml.versions import get_active_config, VERSIONS, ACTIVE_VERSION


def load_features_module(module_name: str = None):
    """动态加载特征模块"""
    if module_name is None:
        module_name = get_active_config()["features_module"]
    return importlib.import_module(module_name)


def run_single(method: str, features_module=None, **kwargs):
    """运行单个标注方案的完整 pipeline"""
    print(f"\n{'=' * 55}")
    print(f"  ML Meta-Labeling — {method}")
    print(f"{'=' * 55}")

    labeled = run_labeling(n_days=5, method=method, **kwargs)

    spy_df = load_spy()
    feat_mod = features_module or load_features_module()
    data, feature_cols = feat_mod.build_features(labeled, spy_df)
    data = data.dropna(subset=feature_cols)
    print(f"[Features] 特征数: {len(feature_cols)}  有效样本: {len(data)}")

    results = train_and_evaluate(data, feature_cols)
    return results


def main():
    parser = argparse.ArgumentParser(description="ML Meta-Labeling MVP")
    parser.add_argument("--method", type=str, default=None,
                        choices=["fixed_horizon", "triple_barrier", "relative_low", "sl_proximity", "sl_multi", "all"],
                        help="标注方法（不指定则使用激活版本配置）")
    args = parser.parse_args()

    if args.method is None:
        config = get_active_config()
        print(f"[Version] 使用激活版本: {ACTIVE_VERSION}")
        method = config["labeling"]["method"]
        kwargs = {k: v for k, v in config["labeling"].items() if k != "method"}
        run_single(method, **kwargs)

    elif args.method == "all":
        print("\n" + "#" * 60)
        print("#  四种标注方案横向对比")
        print("#" * 60)

        configs = [
            ("fixed_horizon", {"horizon": 5}),
            ("triple_barrier", {"tp": 0.02, "sl": -0.03, "max_days": 20}),
            ("relative_low", {"window": 20}),
            ("sl_proximity", {"sl_n": 7, "k": 3}),
        ]
        all_results = {}
        for method, kwargs in configs:
            all_results[method] = run_single(method, **kwargs)

        print("\n" + "=" * 60)
        print("  横向对比总结")
        print("=" * 60)
        print(f"{'方法':<20} {'AUC-ROC':>8} {'AUC-PR':>8} {'正标签%':>8}")
        print("-" * 50)
        for method, res in all_results.items():
            print(f"{method:<20} {res.get('auc_roc', 0):>8.3f} "
                  f"{res.get('auc_pr', 0):>8.3f} {res.get('pos_rate', 0):>7.1%}")
    else:
        kwargs = {}
        if args.method == "fixed_horizon":
            kwargs = {"horizon": 5}
        elif args.method == "triple_barrier":
            kwargs = {"tp": 0.02, "sl": -0.03, "max_days": 20}
        elif args.method == "relative_low":
            kwargs = {"window": 20}
        elif args.method == "sl_proximity":
            kwargs = {"sl_n": 7, "k": 3}
        run_single(args.method, **kwargs)


if __name__ == "__main__":
    main()
