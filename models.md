
- 硅基流动
    - Qwen/Qwen3.5-9B RPM 为 1,000；TPM 为 80,000
    - SiliconFlow_API_KEY
    - Qwen/Qwen3.8-27B RPM 为 1,000；TPM 为 40,000；
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.siliconflow.cn/v1"
)

response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V4-Flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, please introduce yourself."}
    ]
)
print(response.choices[0].message.content)
