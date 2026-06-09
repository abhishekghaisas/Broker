// client/app.js

let ws = null;
let audioContext;
let mediaStream;
let processor;

//Initialize the playback audio context
const playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
let nextStartTime = 0; 

const SAMPLE_RATE = 16000;
//Instantiate your VAD from vad.js (Make sure vad.js is loaded in index.html before app.js)
const vad = new VoiceActivityDetector(0.015);

const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const logDiv = document.getElementById('log');

function logMessage(msg) {
    logDiv.innerHTML += `> ${msg}<br>`;
    logDiv.scrollTop = logDiv.scrollHeight;
}

// ---------------------------------------------------------
//WebSocket Connection Manager
// ---------------------------------------------------------
function connectWebSocket() {
    //If a connection is already open or opening, return it
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return ws;
    }
    
    //Update this URL if your FastAPI backend runs on a different port/route
    ws = new WebSocket('ws://localhost:8000/stream'); 
    
    ws.onopen = () => {
        console.log('🟢 [Network] Connected to Event Broker.');
    };

    ws.onmessage = async (event) => {
    // 1. DATA PLANE: Check if the incoming packet is a UI JSON String
        if (typeof event.data === "string") {
            try {
                const uiData = JSON.parse(event.data);
            
                // Render the puzzle if a terminal tag is received
                if (uiData.type === "terminal") {
                    const puzzleOverlay = document.getElementById('puzzle-overlay');
                    if (puzzleOverlay) {
                        puzzleOverlay.style.display = 'block';
                        document.getElementById('puzzle-desc').innerText = uiData.content;
                    }
                }
            
                // Optional: Handle system alerts
                if (uiData.type === "system_alert") {
                    console.warn("SYSTEM ALERT:", uiData.content);
                }

                // INSTANT SYNC: Force the HUD to update the exact moment the LLM acts
                // This solves your credits not updating in real-time!
                updateHUD(); 

            } catch (err) {
                console.error("⚠️ [UI Parser Error]:", err);
            }
            return; // Halt execution so it doesn't try to play this text as audio
        }

        // 2. AUDIO PLANE: Handle binary audio blobs natively
        try {
            const arrayBuffer = await event.data.arrayBuffer();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.start();
        } catch (err) {
            console.error("⚠️ [Audio Playback Error]:", err);
        }
    };

    // Add this to allow you to close the puzzle visually once you answer it verbally
    document.getElementById('bypassBtn').addEventListener('click', () => {
        document.getElementById('puzzle-overlay').style.display = 'none';
    });
}
// Microphone & VAD Processor
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
        
        //Simplified VAD State
        let isSpeaking = false;

        processor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            
            //Convert Float32 to Int16 PCM
            const int16Array = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                int16Array[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
            }

            //Run Voice Activity Detection
            const speechDetected = vad.hasSpeech(int16Array);

            if (speechDetected) {
                //Speech Detected
                if (!isSpeaking) {
                    console.log("🎙️ [VAD] Speech detected. Transmitting...");
                    isSpeaking = true;
                    // Ensure WebSocket is open before we start streaming
                    ws = connectWebSocket();
                }

                //Stream the bytes to the Python broker
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(int16Array.buffer);
                }
            } else {
                //Silence Detected
                if (isSpeaking) {
                    console.log("⏱️ [VAD] User paused. Holding connection open for AI response...");
                    isSpeaking = false;
                }
                //We do NOTHING else. We stop sending bytes, but we leave the WebSocket open.
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

async function updateHUD() {
    try {
        const response = await fetch('http://localhost:8000/state');
        if (!response.ok) {
            // This prints the actual error message from the server
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Server error');
        }
        const state = await response.json();
        
        // Update your HUD elements
        document.getElementById('loc').innerText = state.location;
        document.getElementById('health').innerText = state.health + "%";
        document.getElementById('credits').innerText = state.credits;
        
        const puzzleOverlay = document.getElementById('puzzle-overlay');
        if (puzzleOverlay) {
            if (state.puzzle) {
                puzzleOverlay.style.display = 'block';
                document.getElementById('puzzle-desc').innerText = state.puzzle;
            } else {
                puzzleOverlay.style.display = 'none';
            }
        }
    } catch (err) {
        console.warn("⚠️ [HUD] Could not sync with backend state.", err.message);
    }
}

setInterval(updateHUD, 3000);