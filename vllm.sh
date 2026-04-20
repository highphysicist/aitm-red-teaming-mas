python -m vllm.entrypoints.openai.api_server \
  --model google/gemma-4-31B-it \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9 \
  --tensor-parallel-size 1