// client/vad.js

class VoiceActivityDetector {
    constructor(energyThreshold = 0.015) {
        // Lower threshold = more sensitive. 0.015 is a standard baseline for near-field mics.
        this.energyThreshold = energyThreshold;
    }

    /**
     * Analyzes an Int16Array of audio to determine if speech is present.
     */
    hasSpeech(int16Array) {
        let sumSquares = 0;
        
        for (let i = 0; i < int16Array.length; i++) {
            // Normalize the 16-bit integer back to a -1.0 to 1.0 float range
            const sample = int16Array[i] / 32768.0;
            sumSquares += sample * sample;
        }
        
        const rms = Math.sqrt(sumSquares / int16Array.length);
        return rms > this.energyThreshold;
    }
}