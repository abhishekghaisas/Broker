import re
import asyncio

class EarlyHeuristicsClassifier:
    def __init__(self):
        # Define ultra-fast Regex patterns for "Ambient" (low-stakes) queries
        self.ambient_patterns = [
            r"^\s*(hello|hi|hey|greetings)\b",
            r"\bhow are you\b",
            r"\bwhat is your name\b",
            r"^\s*test(ing)?\s*$",
            r"^\s*check(ing)?\s*$"
        ]
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.ambient_patterns]

    async def classify(self, text: str) -> str:
        """
        Intercepts transcripts to route them.
        Returns 'ambient' for simple chatter, or 'llm' for complex game logic.
        """
        # We use asyncio to ensure this doesn't block the router's main thread
        await asyncio.sleep(0.001) 
        
        # Check against early heuristics
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return "ambient"
        
        # If it doesn't match ambient chatter, route to the expensive LLM
        return "llm"

# Instantiate a single global instance for the router to import
intent_classifier = EarlyHeuristicsClassifier()