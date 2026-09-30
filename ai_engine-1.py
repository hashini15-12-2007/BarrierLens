from llama_cpp import Llama
import os


MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "models",
    "qwen3-0.6b-Q6_K.gguf"
)


if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(
        f"Model not found: {MODEL_PATH}"
    )


llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=2048,
    n_threads=4,
    verbose=False
)


def analyze_report(description):

    result = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an accessibility assistant. "
                    "Analyze accessibility reports and answer clearly "
                    "in English."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Analyze this accessibility report:\n"
                    f"{description}\n"
                    f"/no_think"
                )
            }
        ],
        max_tokens=120,
        temperature=0.2
    )

    response = result["choices"][0]["message"]["content"].strip()

    return response