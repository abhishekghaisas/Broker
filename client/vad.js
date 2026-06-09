// client/vad.js

class VoiceActivityDetector {
    constructor(threshold = 0.015) {
        // Lower threshold = more sensitive. 0.015 is a standard baseline.
        this.threshold = threshold;
    }

    /**
     * Analyzes a Float32Array of audio to determine if speech is present.
     */
    process(float32Array) {
        let sumSquares = 0.0;
        
        for (let i = 0; i < float32Array.length; i++) {
            // Data is already between -1.0 and 1.0, no need to divide by 32768
            sumSquares += float32Array[i] * float32Array[i];
        }
        
        const rms = Math.sqrt(sumSquares / float32Array.length);
        
        // Returns true if the volume exceeds the noise threshold
        return rms > this.threshold; 
    }
}