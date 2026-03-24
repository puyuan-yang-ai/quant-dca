"""
数据加载模块
负责读取 CSV 文件并解析为可处理的数据结构
"""
import csv
from datetime import datetime


def load_data(filepath, start_date=None, end_date=None):
    """
    加载 SOXL 历史数据
    
    Args:
        filepath: CSV 文件路径
        start_date: 起始日期 (YYYY-MM-DD)，可选
        end_date: 结束日期 (YYYY-MM-DD)，可选
    
    Returns:
        按日期排序的数据列表，每项包含 date, open, high, low, close
    """
    data = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {
                'date': row['时间'],
                'open': float(row['开盘价']),
                'high': float(row['最高价']),
                'low': float(row['最低价']),
                'close': float(row['收盘价'])
            }
            data.append(record)
    
    # 按日期排序
    data.sort(key=lambda x: x['date'])
    
    # 过滤日期范围
    if start_date:
        data = [d for d in data if d['date'] >= start_date]
    if end_date:
        data = [d for d in data if d['date'] <= end_date]
    
    return data

