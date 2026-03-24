"""
图表绘制模块
生成 DCA 策略 vs SOXL 持有收益率对比图
"""
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def save_chart(result, output_dir):
    """
    绘制并保存收益率对比图
    
    Args:
        result: run_backtest() 返回的结果字典
        output_dir: 图片保存目录
    """
    # 解析日期
    dates = [datetime.strptime(d, '%Y-%m-%d') for d in result['dates']]
    dca_returns = [r * 100 for r in result['daily_dca_returns']]  # 转为百分比
    hold_returns = [r * 100 for r in result['daily_hold_returns']]
    smh_returns = [r * 100 for r in result['daily_smh_returns']]
    smh_dca_returns = [r * 100 for r in result.get('daily_smh_dca_returns', [])]
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # 绘制曲线
    ax.plot(dates, dca_returns, color='#5DADE2', linewidth=1.5, label='SOXL DCA')
    ax.plot(dates, hold_returns, color='#F1948A', linewidth=1.5, label='SOXL Buy & Hold')
    ax.plot(dates, smh_returns, color='#8B4513', linewidth=1.5, label='SMH Buy & Hold')
    if smh_dca_returns:
        ax.plot(dates, smh_dca_returns, color='#2ECC71', linewidth=1.5, label='SMH DCA')
    
    # 零线
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
    
    # 标注最终收益率
    final_dca = dca_returns[-1]
    final_hold = hold_returns[-1]
    final_smh = smh_returns[-1]
    ax.annotate(f'{final_dca:.1f}%', xy=(dates[-1], final_dca), 
                xytext=(5, 0), textcoords='offset points', color='#5DADE2', fontsize=10)
    ax.annotate(f'{final_hold:.1f}%', xy=(dates[-1], final_hold),
                xytext=(5, 0), textcoords='offset points', color='#F1948A', fontsize=10)
    ax.annotate(f'{final_smh:.1f}%', xy=(dates[-1], final_smh),
                xytext=(5, 0), textcoords='offset points', color='#8B4513', fontsize=10)
    if smh_dca_returns:
        final_smh_dca = smh_dca_returns[-1]
        ax.annotate(f'{final_smh_dca:.1f}%', xy=(dates[-1], final_smh_dca),
                    xytext=(5, 0), textcoords='offset points', color='#2ECC71', fontsize=10)
    
    # 标注最大回撤点
    dd_idx = result['max_drawdown_idx']
    dd_value = dca_returns[dd_idx]
    ax.scatter([dates[dd_idx]], [dd_value], color='red', s=50, zorder=5)
    ax.annotate(f'Max DD\n{result["max_drawdown"]*100:.1f}%', 
                xy=(dates[dd_idx], dd_value),
                xytext=(-50, -30), textcoords='offset points',
                fontsize=9, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=0.8))
    
    # X 轴日期自动间隔
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=45)
    
    # 标题和标签
    ax.set_title(f'SOXL DCA vs SMH DCA vs Buy & Hold\nPeriod: {result["start_date"]} ~ {result["end_date"]}',
                 fontsize=12)
    ax.set_xlabel('Date')
    ax.set_ylabel('Return (%)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图片
    os.makedirs(output_dir, exist_ok=True)
    filename = datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.png'
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=150)
    plt.close()
    
    print(f'图表已保存：{filepath}')
    return filepath

