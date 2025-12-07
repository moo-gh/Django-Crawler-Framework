from django.db import models
from decimal import Decimal

from reusable.models import BaseModel


class LLMModel(BaseModel):
    """Define available LLM models and their pricing."""

    PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google"),
    ]

    name = models.CharField(
        max_length=100, unique=True, help_text="Model identifier (e.g., gpt-3.5-turbo)"
    )
    display_name = models.CharField(
        max_length=100, help_text="Human-readable name (e.g., GPT-3.5 Turbo)"
    )
    provider = models.CharField(
        max_length=50, choices=PROVIDER_CHOICES, default="openai"
    )

    # Pricing per 1K tokens (in USD)
    input_token_price = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.0000"),
        help_text="Price per 1K input tokens",
    )
    output_token_price = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.0000"),
        help_text="Price per 1K output tokens",
    )

    # Model capabilities
    max_tokens = models.IntegerField(default=4096, help_text="Maximum context length")
    is_active = models.BooleanField(
        default=True, help_text="Whether this model is available for use"
    )
    description = models.TextField(
        blank=True, null=True, help_text="Model description and capabilities"
    )

    # Model metadata
    version = models.CharField(
        max_length=50, blank=True, null=True, help_text="Model version"
    )
    release_date = models.DateField(
        null=True, blank=True, help_text="When this model was released"
    )

    class Meta:
        ordering = ["provider", "name"]
        verbose_name = "LLM Model"
        verbose_name_plural = "LLM Models"

    def __str__(self):
        return f"{self.display_name} ({self.provider})"

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate the cost for given token usage."""
        input_cost = (Decimal(input_tokens) / Decimal("1000")) * self.input_token_price
        output_cost = (
            Decimal(output_tokens) / Decimal("1000")
        ) * self.output_token_price
        return input_cost + output_cost

    @classmethod
    def get_by_name(cls, name: str):
        """Get model by name, case-insensitive."""
        return cls.objects.filter(name__iexact=name, is_active=True).first()

    @classmethod
    def get_default_model(cls):
        """Get the default model for new users."""
        return cls.objects.filter(is_active=True).first()


class LLMUsage(BaseModel):
    """Track individual LLM API calls and their costs."""

    USAGE_TYPES = [
        ("Message Formatting", "Message Formatting"),
    ]

    model = models.ForeignKey(LLMModel, on_delete=models.CASCADE)
    usage_type = models.CharField(max_length=30, choices=USAGE_TYPES)

    # Request details
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    # Cost tracking
    input_cost = models.DecimalField(
        max_digits=10, decimal_places=6, default=Decimal("0.0000")
    )
    output_cost = models.DecimalField(
        max_digits=10, decimal_places=6, default=Decimal("0.0000")
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=6, default=Decimal("0.0000")
    )

    # Request metadata
    request_id = models.CharField(max_length=255, blank=True, null=True)
    model_version = models.CharField(max_length=50, blank=True, null=True)
    response_time_ms = models.IntegerField(null=True, blank=True)

    # Status tracking
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.model} - {self.usage_type} ({self.total_cost}$)"

    def save(self, *args, **kwargs):
        # Calculate costs if not already set
        if self.total_cost == Decimal("0.0000"):
            self.input_cost = (
                Decimal(self.prompt_tokens) / Decimal("1000")
            ) * self.model.input_token_price
            self.output_cost = (
                Decimal(self.completion_tokens) / Decimal("1000")
            ) * self.model.output_token_price
            self.total_cost = self.input_cost + self.output_cost

        # Calculate total tokens if not set
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens

        super().save(*args, **kwargs)


class Formatter(BaseModel):
    instructions = models.TextField()

    def format(self, message: str) -> str:
        """
        Format a message using the formatter's instructions.

        Args:
            message: The raw message to format

        Returns:
            The formatted message, or the original message if formatting fails
        """
        from ai.utils import format_message

        formatted_message = format_message(self.instructions, message)
        if formatted_message is None:
            return message
        return formatted_message
