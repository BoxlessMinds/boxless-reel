"""Embedding function used by both knowledge bases (transcripts and documents)."""

import logging
import os
from functools import cached_property

from lancedb.embeddings import get_registry, register
from lancedb.embeddings.openai import OpenAIEmbeddings

from src.agents.config import AgentConfig

logger = logging.getLogger(__name__)

# Vector sizes of the OpenAI embedding models, keyed by model name without a
# provider prefix
OPENAI_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

# Name of the LanceDB variable holding the OpenRouter key. LanceDB refuses
# API keys written straight into an embedding function's settings, since those
# settings are saved with the table.
OPENROUTER_KEY_VARIABLE = "openrouter_api_key"


@register("openrouter")
class OpenRouterEmbeddings(OpenAIEmbeddings):
    """
    OpenAI embedding models reached through OpenRouter.

    OpenRouter names them with a provider prefix ("openai/text-embedding-3-small"),
    which LanceDB's OpenAI class doesn't recognise when working out the vector size.
    """

    @cached_property
    def _ndims(self) -> int:
        """Return the vector size for the model, ignoring the provider prefix."""
        if self.dim:
            return self.dim
        base_name = self.name.split("/", 1)[-1]
        if base_name not in OPENAI_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Unknown embedding model {self.name!r}. Supported: "
                + ", ".join(f"openai/{name}" for name in OPENAI_EMBEDDING_DIMENSIONS)
            )
        return OPENAI_EMBEDDING_DIMENSIONS[base_name]


def create_embedding_function(config: AgentConfig):
    """
    Create the LanceDB embedding function for the configured provider.

    Uses OpenAI directly when OPENAI_API_KEY is set, and OpenRouter otherwise
    (see AgentConfig.embedding_connection).

    Args:
        config: Agent configuration holding the model name and API keys.

    Returns:
        LanceDB embedding function instance.
    """
    model_name, api_key, base_url = config.embedding_connection
    registry = get_registry()

    if base_url is None:
        # LanceDB's OpenAI client reads the key from the environment
        if api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = api_key
        return registry.get("openai").create(name=model_name)

    logger.debug("Creating OpenRouter embedding function for %s", model_name)
    registry.set_var(OPENROUTER_KEY_VARIABLE, api_key)
    base_name = model_name.split("/", 1)[-1]
    return registry.get("openrouter").create(
        name=model_name,
        base_url=base_url,
        api_key=f"$var:{OPENROUTER_KEY_VARIABLE}",
        # Send the size explicitly rather than null
        dim=OPENAI_EMBEDDING_DIMENSIONS.get(base_name),
    )
