#integrations/classifier.py

import re

class EarlyHeuristicsClassifier:
    def __init__(self):
        #Define our low-stakes ambient queries and their instant cached responses
        self.intent_map = {
            r"^(who is alan|tell me about alan)": "Alan is a rogue synth in the Neon District.",
            r"^(where am i|what is my location)": "You are currently securely logged in at the safehouse.",
            r"^(is it safe|what is the status)": "The area is clear. No hostile entities detected."
        }
        
        #Compile regexes for ultra-fast matching
        self.compiled_intents = {re.compile(pattern, re.IGNORECASE): response for pattern, response in self.intent_map.items()}

    def predict_intent(self, partial_text: str) -> str | None:
        """
        Scans mid-sentence partial transcripts for early intent recognition.
        Returns the cached string response if a match is found, otherwise None.
        """
        clean_text = partial_text.strip().lower()
        
        for pattern, response in self.compiled_intents.items():
            if pattern.search(clean_text):
                print(f"⚡ [Heuristics] Intent intercepted early: '{clean_text}'")
                return response
                
        return None

#Instantiate the fast classifier
intent_classifier = EarlyHeuristicsClassifier()