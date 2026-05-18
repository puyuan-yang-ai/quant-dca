## 8B 系列（基于 Qwen3-8B）

| model | Overall average | HIP OOD average | HIP average | CUDA average | CPP average | Assembly average |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-8B | 27.2425 | 16.02 | 33.8 | 35.62 | 23.53 | |
| pretrain-v1-gs400 | 33.2875 | 23.62 | 42.18 | 41.82 | 25.53 | |
| pretrain-v1-gs400-fim-gs240 | 36.645 | 28.5 | 45.62 | 41.17 | 31.29 | |
| pretrain-v1-gs800 | 33.0425 | 21.74 | 43.31 | 41.95 | 25.17 | |
| pretrain-v1-gs1200 | 32.48 | 20.62 | 42.29 | 41.41 | 25.6 | |
| pretrain-fim-v1-gs400 | 21.47 | 21.47 | | | | |
| pretrain-fim-v1-gs600 | 25.83 | 25.83 | | | | |
| pretrain-fim-v1-gs800 | 23.61 | 23.61 | | | | |
| pretrain-fim-v1-gs1200 | 20.1 | 20.1 | | | | |
| pretrain-v2-gs300 | 31.04 | 23.79 | 38.32 | 38.38 | 23.67 | |
| pretrain-v2-gs600 | 32.7375 | 24.59 | 40.76 | 40.69 | 24.91 | |
| pretrain-v2-gs900 | 33.105 | 23.3 | 41.56 | 41.56 | 26 | |
| pretrain-v2-gs1200 | 33.065 | 22.69 | 41.16 | 42.17 | 26.24 | |
| pretrain-v2-gs1500 | 34.41 | 27.27 | 42.31 | 42.27 | 25.79 | |
| pretrain-v2-gs1500-vllm-wk4 | 32.8225 | 25.07 | 38.92 | 40.53 | 26.77 | |
| pretrain-8B-v2-gs1500-fim-gs180 | 38.5275 | 28.54 | 46.17 | 48.63 | 30.77 | |
| pretrain-v2-gs1500-fim-gs240 | 37.145 | 24.96 | 45.46 | 48.38 | 29.78 | |
| pretrain-v3-gs600-vllm-wk4 | 33.0475 | 26.2 | 38.83 | 39.64 | 27.52 | |
| pretrain-v3-gs900-vllm-wk4 | 32.415 | 24.83 | 37.96 | 37.89 | 28.98 | |
| pretrain-v3-gs1200-vllm-wk4 | 33.295 | 26.44 | 40.19 | 38.4 | 28.15 | |
| pretrain-v3-gs1200-FIM-gs180-vllm-wk4 | 39.835 | 28.58 | 47.83 | 51.14 | 31.79 | |
| pretrain-v3-gs1200-FIM-gs240-vllm-wk4 | 39.7875 | 28.06 | 48.01 | 50.64 | 32.44 | |

---

## Coder 系列（基于 Qwen3-Coder-30B-A3B）

| model | Overall average | HIP OOD average | HIP average | CUDA average | CPP average | Assembly average |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-Coder-30B-A3B | 29.68 | 15.37 | 35.73 | 38.08 | 29.54 | |
| Coder-pretrain-v1-gs200 | 34.5075 | 20.26 | 42.35 | 42.78 | 32.64 | |
| Coder-pretrain-v1-gs400 | 35.0875 | 20.13 | 43.42 | 43.1 | 33.7 | |
| Coder-pretrain-v1-gs600 | 35.585 | 20.3 | 43.77 | 43.31 | 34.96 | |
| Coder-pretrain-v1-gs600-vllm-wk4 | 38.19 | 23.23 | 45.38 | 47.53 | 36.62 | |
| Coder-pretrain-v2-gs1500-vllm-wk4 | 37.875 | 24.29 | 43.54 | 44.98 | 38.69 | |
| Coder-pretrain-v3-gs600-vllm-wk4 | 37.835 | 24.26 | 43.2 | 46.4 | 37.48 | |
| Coder-pretrain-v3-gs900-vllm-wk4 | 39.3275 | 29.9 | 43.7 | 45.83 | 37.88 | 14.69 |
| Coder-pretrain-v3-gs1200-vllm-wk4 | 38.5875 | 26.81 | 43.44 | 45.5 | 38.6 | |
| Coder-pretrain-v3-gs1500-vllm-wk4 | 38.11 | 26.11 | 43.86 | 46.4 | 36.07 | |
| Coder-pretrain-v3-gs900-fim-gs180-vllm-wk4 | 38.6175 | 27.84 | 43.36 | 45.87 | 37.4 | |
| Coder-pretrain-v3-lr1e-5-gs600-vllm-wk4 | 37.895 | 24.96 | 44.23 | 44.5 | 37.89 | |
| Coder-pretrain-v3-gs900-fim-gs240-vllm-wk4 | 37.835 | 26.96 | 42.36 | 44.04 | 37.98 | |
| Coder-pretrain-v4-gs1000-vllm-wk4 | 37.93 | 23.59 | 43.19 | 46.57 | 38.37 | |
| Coder-pretrain-v4-gs1500-vllm-wk4 | 37.6925 | 26.33 | 41.53 | 44.56 | 38.35 | |
| Coder-pretrain-v4-gs2500-vllm-wk4 | 37.82 | 24.59 | 42.68 | 45.25 | 38.76 | 36.55 |
| Coder-pretrain-v4-gs1000-lr2e-5-vllm-wk4 | 33.27 | 21.97 | 36.17 | 38.1 | 36.84 | 36.37 |
| Coder-pretrain-v4-gs1500-lr2e-5-vllm-wk4 (1) | 34.435 | 25.45 | 36.34 | 38.44 | 37.51 | 36.55 |
| Coder-pretrain-v4-gs1500-lr2e-5-vllm-wk4 (2) | 36.7 | 26.53 | 40.9 | 41.55 | 37.82 | 38.57 |

---

## 14B 系列（基于 Qwen3-14B）

| model | Overall average | HIP OOD average | HIP average | CUDA average | CPP average | Assembly average |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-14B | 22.8075 | 15.37 | 25.74 | 30.21 | 19.91 | |
| Qwen3-14B-pretrain-v3-gs900 | 29.2325 | 20.81 | 34.76 | 33.09 | 28.27 | |
| Qwen3-14B-pretrain-v3-gs1200 | 29.0525 | 22.57 | 32.73 | 32.51 | 28.4 | |
| Qwen3-14B-pretrain-v3-gs1500 | 29.065 | 20.9 | 33.85 | 33.03 | 28.48 | |
| Qwen3-14B-pretrain-v3-gs2100 | 28.705 | 21.86 | 32.53 | 31.28 | 29.15 | |
| Qwen3-14B-pretrain-v3-gs1200-FIM240 | 36.39 | 25.16 | 43.04 | 45.46 | 31.9 | |
| Qwen3-14B-pretrain-v3-gs1200-FIM300 | 36.4875 | 27.08 | 41.92 | 44.75 | 32.2 | |
| Qwen3-14B-pretrain-v3-3epoch-gs900 | 30.68 | 22.96 | 35.56 | 35.22 | 28.98 | |
| Qwen3-14B-pretrain-v3-3epoch-gs1200 | 30.155 | 23.56 | 34.35 | 34.81 | 27.9 | |
| Qwen3-14B-pretrain-v3-3epoch-gs1200-FIM240 | 37.465 | 28.71 | 43.85 | 44.51 | 32.79 | |
| Qwen3-14B-pretrain-v3-3epoch-lr8e-6-gs1200 | 29.8425 | 23.25 | 35.18 | 33.04 | 27.9 | |
| Qwen3-14B-pretrain-v3-3epoch-lr8e-6-gs1200-FIM-240 | 37.9975 | 26.22 | 45.42 | 46.5 | 33.85 | |
| Qwen3-14B-pretrain-v3-3epoch-lr8e-6-gs1200-FIM-300 | 37.7425 | 26.74 | 44.3 | 46.97 | 32.96 | |
| Qwen3-14B-pretrain-v3-3epoch-lr8e-6-gs1200-FIM-lr8e-6-240 | 35.7725 | 27.75 | 41.71 | 42.02 | 31.61 | |
| Qwen3-14B-pretrain-v3-3epoch-lr8e-6-gs1200-FIM-4epoch-240 | 38.0675 | 28.46 | 44.94 | 45.85 | 33.02 | |

---

## 14B 汇总对比

| 实验配置 | continuation | FIM | 平均 |
| --- | --- | --- | --- |
| 8B 最优 | 39.7875 | 44.05 | 41.91875 |
| 14B 最优 | 36.39 | 48.195 | 42.2925 |
| 默认 lr schedule | 37.465 | 47.7575 | 42.61125 |
| 默认 lr schedule + 调整 pretrain lr | 37.9975 | 47.4925 | 42.745 |
| 默认 lr schedule + 调整 pretrain lr + 调整 FIM lr | 35.7725 | 47.835 | 41.80375 |
| 默认 lr schedule + 调整 pretrain lr + 调整 FIM lr schedule | 38.0675 | 46.945 | 42.50625 |
