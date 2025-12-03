# services/llm/run.py
from logger.config import init_logging
from services.llm.errors import LLMError
from services.llm.factory import LLMClientType, LLMFactory
from services.llm.schemas import LLMOptions, LLMRequest

init_logging()


def main():
    try:
        factory = LLMFactory()
        client = factory.build(
            llm_client=LLMClientType.OPENAI,
            options=LLMOptions(
                model="gpt-4o-mini",
                api_key=None,  # pull from env if None
                model_params={"temperature": 0.0},
            ),
        )

        req = LLMRequest(
            user_prompt="List 3 colors as json array ",
            system_prompt="You are a strict JSON generator.",
        )
        resp = client.generate(req)

        print("-" * 120)
        print("LLM response:", resp)

    except LLMError as e:
        print("LLM error:", e)


if __name__ == "__main__":
    main()
