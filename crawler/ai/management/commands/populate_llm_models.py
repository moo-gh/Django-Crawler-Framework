from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from ai.models import LLMModel


class Command(BaseCommand):
    help = "Populate LLM models with default pricing and configuration"

    def handle(self, *args, **options):
        """Create default LLM models with current pricing."""

        models_data = [
            {
                "name": "gpt-3.5-turbo",
                "display_name": "GPT-3.5 Turbo",
                "provider": "openai",
                "input_token_price": Decimal("0.0005"),
                "output_token_price": Decimal("0.0015"),
                "max_tokens": 4096,
                "description": "Fast and efficient model for most tasks",
                "version": "stable",
                "release_date": date(2023, 6, 13),
            },
            {
                "name": "gpt-3.5-turbo-16k",
                "display_name": "GPT-3.5 Turbo 16K",
                "provider": "openai",
                "input_token_price": Decimal("0.003"),
                "output_token_price": Decimal("0.004"),
                "max_tokens": 16384,
                "description": "GPT-3.5 Turbo with extended context",
                "version": "stable",
                "release_date": date(2023, 6, 13),
            },
            {
                "name": "gpt-4",
                "display_name": "GPT-4",
                "provider": "openai",
                "input_token_price": Decimal("0.03"),
                "output_token_price": Decimal("0.06"),
                "max_tokens": 8192,
                "description": "Most capable GPT-4 model",
                "version": "0613",
                "release_date": date(2023, 3, 14),
            },
            {
                "name": "gpt-4-turbo",
                "display_name": "GPT-4 Turbo",
                "provider": "openai",
                "input_token_price": Decimal("0.01"),
                "output_token_price": Decimal("0.03"),
                "max_tokens": 128000,
                "description": "GPT-4 Turbo with extended context and lower cost",
                "version": "1106",
                "release_date": date(2023, 11, 6),
            },
            {
                "name": "gpt-4.1",
                "display_name": "GPT-4.1",
                "provider": "openai",
                "input_token_price": Decimal("0.03"),
                "output_token_price": Decimal("0.06"),
                "max_tokens": 1000000,
                "description": "Next-generation GPT model with larger context and improved capabilities",
                "version": "4.1",
            },
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
                "provider": "openai",
                "input_token_price": Decimal("0.0025"),
                "output_token_price": Decimal("0.01"),
                "max_tokens": 128000,
                "description": "GPT-4o optimized for speed and efficiency",
                "version": "o",
                "release_date": date(2024, 5, 13),
            },
            {
                "name": "gpt-4o-mini",
                "display_name": "GPT-4o Mini",
                "provider": "openai",
                "input_token_price": Decimal("0.00015"),
                "output_token_price": Decimal("0.0006"),
                "max_tokens": 128000,
                "description": "Smaller, cost-efficient GPT-4o variant (text + vision capable)",
                "version": "gpt-4o-mini-20240718",
                "release_date": date(2024, 7, 18),
            },
        ]

        created_count = 0
        updated_count = 0

        for model_data in models_data:
            model, created = LLMModel.objects.get_or_create(
                name=model_data["name"], defaults=model_data
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created model: {model.display_name}")
                )
            else:
                for key, value in model_data.items():
                    if key != "name":
                        setattr(model, key, value)
                model.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f"Updated model: {model.display_name}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully processed {len(models_data)} models. "
                f"Created: {created_count}, Updated: {updated_count}"
            )
        )
