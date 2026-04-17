"""
实验批量运行入口
用法：python run_experiments.py
"""
from experiments.runner import run_all_experiments


if __name__ == '__main__':
    results = run_all_experiments()
