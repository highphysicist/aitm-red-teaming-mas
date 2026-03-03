import asyncio
from metagpt.llm import LLM

async def main():
    print("Initializing MetaGPT LLM Engine...")
    
    # This automatically reads your config/config2.yaml file
    llm = LLM() 
    
    print("Pinging Ollama... (waiting for response)")
    
    # Send a direct, asynchronous prompt to the model
    response = await llm.aask("Hello! Are you successfully connected? Please reply with a short, 1-sentence confirmation.")
    
    print("\n" + "="*40)
    print("SUCCESS! META-GPT RESPONSE:")
    print("="*40)
    print(response)
    print("="*40 + "\n")

if __name__ == '__main__':
    asyncio.run(main())