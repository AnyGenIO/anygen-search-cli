import os

# Provide dummy keys so providers think they're configured during tests.
for k in [
    "BRAVE_API_KEY",
    "SERPER_API_KEY",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "JINA_API_KEY",
]:
    os.environ.setdefault(k, "test-" + k.lower())
