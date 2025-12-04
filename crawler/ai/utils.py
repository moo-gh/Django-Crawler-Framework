import os
import time
from typing import Optional

from openai import OpenAI

from ai.models import LLMUsage


def query_openai(
    query: str,
    model: str = "gpt-3.5-turbo",
    usage_type: str = "custom",
) -> Optional[str]:
    """
    Query OpenAI API with usage tracking.

    Args:
        query: The prompt to send to the model
        model: The model to use (default: gpt-3.5-turbo)
        usage_type: Type of usage for categorization

    Returns:
        The response content or None if failed
    """
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        organization=os.environ.get("OPENAI_ORG_ID"),
    )

    start_time = time.time()
    usage_record = None

    try:
        # Make the API call
        result = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": query,
                }
            ],
            model=model,
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Extract usage information
        usage = result.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens

        # Create usage record if profile is provided
        usage_record = LLMUsage.objects.create(
            usage_type=usage_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model_version=model,
            response_time_ms=response_time_ms,
            success=True,
        )

        # Check if the response was completed successfully
        if result.choices[0].finish_reason != "stop":
            if usage_record:
                usage_record.success = False
                usage_record.error_message = (
                    f"Unexpected finish reason: {result.choices[0].finish_reason}"
                )
                usage_record.save()
            return None

        return result.choices[0].message.content

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return None


def format_message(instructions: str, raw_message: str) -> str:
    """
    Format a raw message using AI instructions.

    Args:
        instructions: The instructions for the AI to follow
        raw_message: The raw message to format

    Returns:
        The formatted message
    """
    return query_openai(
        f"Format the following message using the following instructions: {instructions}\n\n{raw_message}"
    )
