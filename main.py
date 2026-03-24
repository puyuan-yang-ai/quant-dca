"""
SOXL 多层次 DCA 策略回测脚本
用法：python main.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
配置：config/settings.yaml（命令行参数优先于配置文件）
"""
import argparse
import importlib
import os
import yaml

from src.data_loader import load_data
from src.backtest import run_backtest
from src.chart import save_chart


def load_config(config_path):
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    # 项目根目录
    root_dir = os.path.dirname(__file__)
    config_dir = os.path.join(root_dir, 'config')
    
    # 两步加载配置：先读取主配置获取场景配置文件名，再加载场景配置
    settings_path = os.path.join(config_dir, 'settings.yaml')
    settings = load_config(settings_path)
    
    scene_config_name = settings.get('use_config', 'default.yaml')
    config_path = os.path.join(config_dir, scene_config_name)
    config = load_config(config_path)
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='SOXL 多层次 DCA 策略回测')
    parser.add_argument('--start-date', type=str, help='回测起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='回测结束日期 (YYYY-MM-DD)')
    args = parser.parse_args()
    
    # 命令行参数优先于配置文件
    start_date = args.start_date or config.get('start_date') or None
    end_date = args.end_date or config.get('end_date') or None
    data_file = config.get('data_file', 'data/SOXL.csv')
    fee_rate = config.get('fee_rate', 0.01)
    
    # 读取订单配置：[[价格系数, 股数], ...] -> [(价格系数, 股数), ...]
    orders_config = config.get('orders')
    orders = [tuple(o) for o in orders_config] if orders_config else None
    
    # 动态加载策略
    strategy_name = config.get('strategy', 'baseline')
    strategy_module = importlib.import_module(f'src.strategies.{strategy_name}')
    execute_day = strategy_module.execute_day
    
    # 数据文件路径
    data_path = os.path.join(root_dir, data_file)
    
    # 加载数据
    print('正在加载数据...')
    print(f'场景配置：{scene_config_name}')
    print(f'使用策略：{strategy_name}')
    data = load_data(data_path, start_date, end_date)
    
    if not data:
        print('错误：没有找到符合条件的数据')
        return
    
    print(f'已加载 {len(data)} 个交易日数据')
    
    # 执行回测
    print('正在执行回测...')
    print(f'订单配置：{orders}')
    result = run_backtest(data, fee_rate, orders, execute_day)
    
    # 加载 SMH 基准数据并计算收益率
    smh_path = os.path.join(root_dir, 'data/SMH_adjusted.csv')
    smh_data = load_data(smh_path, start_date, end_date)
    smh_first_close = smh_data[0]['close']
    
    # SMH Buy & Hold 收益率
    result['daily_smh_returns'] = [
        (d['close'] - smh_first_close) / smh_first_close 
        for d in smh_data
    ]
    
    # SMH DCA 收益率（与 SOXL DCA 相同的定投策略）
    smh_total_shares = 0.0
    smh_total_cost = 0.0
    smh_dca_returns = []
    for day in smh_data:
        # 执行当日 DCA 策略
        day_orders = execute_day(day['open'], day['low'], fee_rate, orders)
        for order in day_orders:
            smh_total_shares += order['shares']
            smh_total_cost += order['cost']
        # 计算当日 DCA 收益率
        smh_daily_value = day['close'] * smh_total_shares
        smh_dca_return = (smh_daily_value - smh_total_cost) / smh_total_cost if smh_total_cost > 0 else 0
        smh_dca_returns.append(smh_dca_return)
    result['daily_smh_dca_returns'] = smh_dca_returns
    
    # 输出结果
    print('\n' + '=' * 50)
    print('SOXL 多层次 DCA 策略回测结果')
    print('=' * 50)
    print(f"回测区间：{result['start_date']} ~ {result['end_date']}")
    print(f"交易天数：{result['trading_days']} 天")
    print('-' * 50)
    print(f"总投入成本：${result['total_cost']:,.2f}")
    print(f"总持股数量：{result['total_shares']:,.4f} 股")
    
    # 输出订单分类统计
    order_stats = result.get('order_stats', {})
    if order_stats:
        # 市价单（price_ratio = 1.0）
        market = order_stats.get(1.0, {'shares': 0, 'cost': 0, 'count': 0})
        print(f"  - 市价单：{market['shares']:,.4f} 股（${market['cost']:,.2f}）成交 {market['count']} 次")
        
        # 限价单汇总
        limit_shares = 0
        limit_cost = 0
        limit_count = 0
        limit_details = []
        for ratio, stats in sorted(order_stats.items(), reverse=True):
            if ratio < 1.0:
                limit_shares += stats['shares']
                limit_cost += stats['cost']
                limit_count += stats['count']
                pct = round((1 - ratio) * 100)
                limit_details.append((pct, stats))
        
        print(f"  - 限价单：{limit_shares:,.4f} 股（${limit_cost:,.2f}）成交 {limit_count} 次")
        for pct, stats in limit_details:
            print(f"    - 跌{pct}%：{stats['shares']:,.4f} 股（${stats['cost']:,.2f}）成交 {stats['count']} 次")
    
    print(f"期末市值：  ${result['final_value']:,.2f}")
    print(f"平均持仓成本：${result['avg_cost']:,.2f}")
    print('-' * 50)
    print(f"总收益：    ${result['total_profit']:,.2f}")
    print(f"总收益率：  {result['total_return'] * 100:,.2f}%")
    print(f"年化收益率：{result['annualized_return'] * 100:,.2f}%")
    print(f"最大回撤：  {result['max_drawdown'] * 100:,.2f}%")
    print(f"夏普比率：  {result['sharpe_ratio']:.2f}")
    print('=' * 50)
    
    # 生成图表
    output_dir = os.path.join(root_dir, 'output')
    save_chart(result, output_dir)


if __name__ == '__main__':
    main()
