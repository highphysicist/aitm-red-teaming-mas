vllm serve google/gemma-4-31b-it \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --dtype bfloat16
