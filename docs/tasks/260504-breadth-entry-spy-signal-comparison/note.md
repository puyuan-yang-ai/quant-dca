问题：Market Breadth 还只是图表观察指标，尚未作为可回测的入场信号，同时项目切换到 SPY 后也需要重新确认 NDayConfirm、RSI、EMA 等 Entry 策略的优劣。

影响：沿用 SOXL 时代的 NDay=5 和旧策略排名可能不适合 SPY，且无法判断 Breadth<20 恐慌买入信号是否真的具备择时优势。

修复方案：新增 BreadthEntry，先搜索 SPY 下最优 NDay 参数，再用统一执行层比较 7 类入场策略，最终确认 NDay5 与 Breadth<20 是 SPY 下最值得保留的两个 Entry 信号。