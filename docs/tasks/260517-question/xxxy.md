🔴 1. XGBoost 的 predict_proba 默认不是真概率(最容易踩的坑)
这个是 90% 初学者会忽略的陷阱。XGBoost / 随机森林 / SVM 输出的 "概率" 都不是校准过的真实概率——0.9 不代表"90% 是真买点",可能实际只有 60%。后果:你按 0.9 重仓,结果 10 次有 4 次错,仓位映射就崩了。

解决方案:用 CalibratedClassifierCV 包一层(Platt scaling 或 isotonic regression):

python
from sklearn.calibration import CalibratedClassifierCV
calibrated_model = CalibratedClassifierCV(xgb_model, method='isotonic', cv='prefit')
校准后 predict_proba 输出 0.9 才真的接近 90%。只有逻辑回归天然就是校准的(这也是它做 baseline 的另一个好处)。

🔴 2. 概率阈值(0.5 / 0.6 / 0.9)不能拍脑袋定,必须用验证集学出来
你写的 "0.6 轻仓 / 0.9 重仓" 是凭直觉的。正确做法:

Code
在验证集上 grid search:
  for 阈值组合 in [(0.5, 0.7), (0.5, 0.8), (0.6, 0.8), (0.6, 0.9), ...]:
    按这个阈值映射仓位 → 跑回测 → 算 Sharpe
选 Sharpe 最高的阈值组合
不同特征 / 不同模型,最优阈值差异很大。最优阈值经常不是 0.5(因为正负样本不均衡)。

🟡 3. 仓位映射不一定要分档,可以连续映射
你想的是"概率 0.6 → 1 档,0.9 → 3 档"这种离散映射。其实可以更平滑:

python
# 方案 A:线性映射(简单)
position = max(0, (proba - 0.5) * 2) * max_position  # 0.5 不买, 1.0 满仓

# 方案 B:Kelly 公式(理论最优,但要估计赔率)
position = (proba * win_amount - (1-proba) * loss_amount) / win_amount

# 方案 C:你说的分档(实操最稳)
实操上分档更稳健(避免概率小幅波动导致仓位剧烈变化),但要知道还有别的选择。