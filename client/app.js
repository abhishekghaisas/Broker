// client/app.js

let ws = null;
let audioContext;
let mediaStream;
let processor;

// Initialize the playback audio context
const playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
let nextStartTime = 0; 

const SAMPLE_RATE = 16000;
// Instantiate your VAD from vad.js (Make sure vad.js is loaded in index.html before app.js)
const vad = new VoiceActivityDetector(0.015);

const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const logDiv = document.getElementById('log');

function logMessage(msg) {
    logDiv.innerHTML += `> ${msg}<br>`;
    logDiv.scrollTop = logDiv.scrollHeight;
}

// ---------------------------------------------------------
// WebSocket Connection Manager
// ---------------------------------------------------------
function connectWebSocket() {
    // If a connection is already open or opening, return it
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return ws;
    }
    
    // NOTE: Update this URL if your FastAPI backend runs on a different port/route
    ws = new WebSocket('ws://localhost:8000/stream'); 
    
    ws.onopen = () => {
        console.log('🟢 [Network] Connected to Event Broker.');
    };

    ws.onmessage = async (event) => {
        let arrayBuffer;
        
        if (event.data instanceof Blob) {
            arrayBuffer = await event.data.arrayBuffer();
        } else {
            console.log("💬 [JSON/Text from Server]:", event.data);
            return; 
        }

        try {
            // Wake up playback context if browser suspended it
            if (playbackCtx.state === 'suspended') {
                await playbackCtx.resume();
            }

            // Let native browser engine decode the Deepgram MP3 bytes
            playbackCtx.decodeAudioData(arrayBuffer, (audioBuffer) => {
                const source = playbackCtx.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(playbackCtx.destination);
                
                const currentTime = playbackCtx.currentTime;
                if (nextStartTime < currentTime) {
                    nextStartTime = currentTime;
                }
                
                source.start(nextStartTime);
                nextStartTime += audioBuffer.duration;
                
            }, (error) => {
                console.error("❌ [Decode Error] Browser failed to decode the MP3:", error);
            });
        } catch (err) {
            console.error("❌ [Fatal Error] Web Audio API crashed during decode:", err);
        }
    };

    ws.onclose = () => {
        console.log('🔴 [Network] Cloud connection closed.');
    };

    ws.onerror = () => {
        console.log('⚠️ [Network] WebSocket Error.');
    };

    return ws;
}

// ---------------------------------------------------------
// Microphone & VAD Processor
// ---------------------------------------------------------
async function startMicrophone() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        logMessage('🎙️ Microphone access granted. Listening for speech...');

        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
        
        if (playbackCtx.state === 'suspended') {
            await playbackCtx.resume();
        }

        const source = audioContext.createMediaStreamSource(mediaStream);
        processor = audioContext.createScriptProcessor(4096, 1, 1);
        
        // Simplified VAD State
        let isSpeaking = false;

        processor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            
            // 1. Convert Float32 to Int16 PCM
            const int16Array = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                int16Array[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
            }

            // 2. Run Voice Activity Detection
            const speechDetected = vad.hasSpeech(int16Array);

            if (speechDetected) {
                // --- SPEECH DETECTED ---
                if (!isSpeaking) {
                    console.log("🎙️ [VAD] Speech detected. Transmitting...");
                    isSpeaking = true;
                    // Ensure WebSocket is open before we start streaming
                    ws = connectWebSocket();
                }

                // Stream the bytes to the Python broker
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(int16Array.buffer);
                }
            } else {
                // --- SILENCE DETECTED ---
                if (isSpeaking) {
                    console.log("⏱️ [VAD] User paused. Holding connection open for AI response...");
                    isSpeaking = false;
                }
                // We do NOTHING else. We stop sending bytes, but we leave the WebSocket open.
            }
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
        
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;

    } catch (err) {
        console.error('Microphone initialization failed:', err);
        logMessage('❌ Failed to access microphone.');
    }
}

function stopMicrophone() {
    if (processor) {
        processor.disconnect();
        processor = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
}

// ---------------------------------------------------------
// UI Controls
// ---------------------------------------------------------
connectBtn.onclick = () => {
    startMicrophone();
};

disconnectBtn.onclick = () => {
    if (ws) {
        ws.close();
        ws = null;
    }
    stopMicrophone();
    logMessage('🛑 System Offline.');
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
};