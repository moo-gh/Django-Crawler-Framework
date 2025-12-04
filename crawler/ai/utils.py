import os
import time
from typing import Optional

from openai import OpenAI
from django.conf import settings

from ai.models import LLMModel, LLMUsage


def _get_llm_model(model_name: str) -> LLMModel:
    """
    Retrieve or lazily create an LLMModel entry for the given model name.
    Ensures usage tracking always has a valid foreign key reference.
    """
    existing_model = LLMModel.get_by_name(model_name)
    if existing_model:
        return existing_model

    llm_model, _ = LLMModel.objects.get_or_create(
        name=model_name,
        defaults={
            "display_name": model_name,
        },
    )
    return llm_model


def _normalize_usage_type(requested_type: Optional[str]) -> str:
    """
    Ensure the usage type matches one of the allowed choices.
    Falls back to the first defined usage type.
    """
    allowed_types = {choice[0] for choice in LLMUsage.USAGE_TYPES}
    if requested_type in allowed_types:
        return requested_type
    return LLMUsage.USAGE_TYPES[0][0]


def query_openai(
    query: str,
    model: str = "gpt-3.5-turbo",
    usage_type: Optional[str] = None,
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
        api_key=settings.OPENAI_API_KEY,
        organization=settings.OPENAI_ORG_ID,
    )

    start_time = time.time()
    llm_model = _get_llm_model(model)
    normalized_usage_type = _normalize_usage_type(usage_type)
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
            model=llm_model,
            usage_type=normalized_usage_type,
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
        f"Format the following message using the following instructions: {instructions}\n\n{raw_message}",
        model="gpt-3.5-turbo",
        usage_type="Message Formatting",
    )
