from django.apps import AppConfig
import atexit
import logging
import os
import sys


logger = logging.getLogger(__name__)
_models_warmed = False
_unload_registered = False


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        global _models_warmed

        if not should_preload_ai_models():
            return

        if _models_warmed:
            return

        try:
            from .ai import warmup_ollama_model
            from .rag import warmup_rag_models

            warmup_rag_models()
            warmup_ollama_model()
            register_ollama_unload()
            _models_warmed = True
            logger.info('StudentAI models loaded and warmed at startup.')
        except Exception as exc:
            logger.warning(
                'StudentAI model warmup failed at startup: %s',
                exc
            )


def should_preload_ai_models():
    preload_setting = os.environ.get('STUDENTAI_PRELOAD_AI', '0').strip().lower()

    if preload_setting not in {'1', 'true', 'yes', 'on'}:
        return False

    management_command = sys.argv[1] if len(sys.argv) > 1 else ''
    skip_commands = {
        'check',
        'collectstatic',
        'makemigrations',
        'migrate',
        'shell',
        'test',
    }

    if management_command in skip_commands:
        return False

    if management_command == 'runserver':
        return os.environ.get('RUN_MAIN') == 'true'

    return True


def register_ollama_unload():
    global _unload_registered

    if _unload_registered:
        return

    def unload_model():
        try:
            from .ai import unload_ollama_model

            unload_ollama_model()
        except Exception:
            logger.debug(
                'StudentAI model unload skipped during shutdown.',
                exc_info=True
            )

    atexit.register(unload_model)
    _unload_registered = True
