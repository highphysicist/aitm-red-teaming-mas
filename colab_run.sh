%%bash
# 1. Install missing dependency and Ollama
apt-get install -y zstd
curl -fsSL https://ollama.com/install.sh | sh

# 2. Start server (Absolute path to ensure it's found)
/usr/local/bin/ollama serve > server.log 2>&1 &

# 3. Wait for server readiness
until curl -s localhost:11434/api/tags > /dev/null; do sleep 2; done

# 4. Pull and Run
/usr/local/bin/ollama pull llama3
/usr/local/bin/ollama pull qwen2.5:32b
python /content/aitm-red-teaming-mas/main.py