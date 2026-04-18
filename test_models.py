import os
import asyncio
import litellm
from dotenv import load_dotenv

load_dotenv('.env')
os.environ['OPENROUTER_API_KEY'] = os.getenv('FORGE_OPEN_ROUTER_KEY')
os.environ['OPENROUTER_API_BASE'] = os.getenv('FORGE_OPEN_BASE_URL', 'https://openrouter.ai/api/v1/')

models = [
    'openrouter/arcee-ai/trinity-large-preview:free',
    'openrouter/nvidia/nemotron-3-super-120b-a12b:free',
    'openrouter/z-ai/glm-4.5-air:free',
    'openrouter/openai/gpt-oss-120b:free',
    'openrouter/minimax/minimax-m2.5:free',
    'openrouter/qwen/qwen3-coder:free'
]

async def test_models():
    print("Starting tests...")
    for model in models:
        try:
            print(f'Testing {model}...')
            response = await litellm.acompletion(
                model=model,
                messages=[{'role': 'user', 'content': 'Hello!'}],
                max_tokens=5
            )
            print(f'[SUCCESS] {model}')
        except Exception as e:
            msg = str(e).split('\n')[0][:100]
            print(f'[ERROR] {model}: {msg}')

asyncio.run(test_models())
