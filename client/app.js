// client/app.js

// Determine backend URL based on environment
const BACKEND_URL = (() => {
    const hostname = window.location.hostname;

    // Production (Vercel domain)
    if (hostname.includes('vercel.app') || (typeof process !== 'undefined' && process.env.NODE_ENV === 'production')) {
        // Get from window variable or environment
        return window.BROKER_BACKEND_URL || 'https://broker-7gxx.onrender.com';
    }

    // Local development (localhost on port 8080)
    return 'http://localhost:8080';
})();

const WS_URL = BACKEND_URL.replace(/^http/, 'ws');

let ws = null;
let audioContext;
let mediaStream;
let processor;

// Initialize the playback audio context
const playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
let nextStartTime = 0; 

const SAMPLE_RATE = 16000;
// Instantiate your VAD from vad.js
const vad = new VoiceActivityDetector(0.015);

const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const logDiv = document.getElementById('log');

function logMessage(msg) {
    if(logDiv) {
        logDiv.innerHTML += `> ${msg}<br>`;
        logDiv.scrollTop = logDiv.scrollHeight;
    }
}

// ---------------------------------------------------------
// DOM Event Listeners (Global Scope - Bind Once)
// ---------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    // 0. Main Menu Handler
    const startMissionBtn = document.getElementById('startMissionBtn');
    if (startMissionBtn) {
        startMissionBtn.addEventListener('click', () => {
            const mainMenu = document.getElementById('main-menu');
            if (mainMenu) mainMenu.style.display = 'none';
        });
    }

    // 1. Bypass Button Binding
    const bypassBtn = document.getElementById('bypassBtn');
    if (bypassBtn) {
        bypassBtn.addEventListener('click', () => {
            const overlay = document.getElementById('puzzle-overlay');
            if (overlay) overlay.style.display = 'none';
        });
    }

    // 1b. Restart after victory — reload for a fresh operation.
    const restartBtn = document.getElementById('restartBtn');
    if (restartBtn) {
        restartBtn.addEventListener('click', () => location.reload());
    }

    // 1c. Restart after loss — reload for a fresh operation.
    const restartLossBtn = document.getElementById('restartLossBtn');
    if (restartLossBtn) {
        restartLossBtn.addEventListener('click', () => location.reload());
    }

    // 2. Keyboard Input Binding
    const submitBtn = document.getElementById('submitPuzzleBtn');
    const puzzleInput = document.getElementById('puzzleInput');

    if (submitBtn && puzzleInput) {
        // Typo fixed here:
        submitBtn.addEventListener('click', sendPuzzleAnswer);
        
        puzzleInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendPuzzleAnswer();
        });

        function sendPuzzleAnswer() {
            const answer = puzzleInput.value.trim();
            if (answer && ws && ws.readyState === WebSocket.OPEN) {
                // Send the text answer as a JSON payload
                ws.send(JSON.stringify({ type: "text_input", text: answer }));
                puzzleInput.value = ''; // Clear the input box
                // Dismiss the puzzle once an answer is submitted.
                const overlay = document.getElementById('puzzle-overlay');
                if (overlay) overlay.style.display = 'none';
            }
        }
    }
});

// ---------------------------------------------------------
// Victory / Game-Over Screen
// ---------------------------------------------------------
function showVictory(summary) {
    const overlay = document.getElementById('victory-overlay');
    if (overlay) {
        const summaryEl = document.getElementById('victory-summary');
        if (summaryEl) summaryEl.innerText = summary || '';
        overlay.style.display = 'flex';
    }

    // The game is over: stop capturing audio and close the link.
    stopMicrophone();
    if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
    }
    if (connectBtn) connectBtn.disabled = false;
    if (disconnectBtn) disconnectBtn.disabled = true;
    const status = document.getElementById('status');
    if (status) status.innerText = "MISSION COMPLETE";
}

function showLoss(summary) {
    const overlay = document.getElementById('loss-overlay');
    if (overlay) {
        const summaryEl = document.getElementById('loss-summary');
        if (summaryEl) summaryEl.innerText = summary || '';
        overlay.style.display = 'flex';
    }

    // The game is over: stop capturing audio and close the link.
    stopMicrophone();
    if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
    }
    if (connectBtn) connectBtn.disabled = false;
    if (disconnectBtn) disconnectBtn.disabled = true;
    const status = document.getElementById('status');
    if (status) status.innerText = "MISSION FAILED";
}

// ---------------------------------------------------------
// WebSocket Connection Manager
// ---------------------------------------------------------
function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    
    ws = new WebSocket(`${WS_URL}/stream`); 
    
    ws.onopen = () => {
        console.log('🟢 [Network] Connected to Event Broker.');
    };

    ws.onmessage = async (event) => {
        const receiveTime = performance.now();

        // 1. DATA PLANE: Check if the incoming packet is a UI JSON String
        if (typeof event.data === "string") {
            try {
                const uiData = JSON.parse(event.data);
                console.log(`[${receiveTime.toFixed(0)}ms] 📨 UI Message: ${uiData.type}`);

                // Render the puzzle if a terminal tag is received
                if (uiData.type === "terminal") {
                    console.log(`[${receiveTime.toFixed(0)}ms] 🖥️ Puzzle received`);
                    const puzzleOverlay = document.getElementById('puzzle-overlay');
                    if (puzzleOverlay) {
                        puzzleOverlay.style.display = 'block';
                        document.getElementById('puzzle-desc').innerText = uiData.content;
                    }
                }

                if (uiData.type === "system_alert") {
                    console.warn(`[${receiveTime.toFixed(0)}ms] ⚠️ SYSTEM ALERT:`, uiData.content);
                }

                // Mission won — show the congratulation window and end the session.
                if (uiData.type === "victory") {
                    console.log(`[${receiveTime.toFixed(0)}ms] 🎉 VICTORY`);
                    showVictory(uiData.content);
                    return;
                }

                // Mission lost — show the failure window and end the session.
                if (uiData.type === "loss") {
                    console.log(`[${receiveTime.toFixed(0)}ms] 💀 LOSS DETECTED`);
                    console.log(`[${receiveTime.toFixed(0)}ms] 💀 Loss message:`, uiData.content);
                    showLoss(uiData.content);
                    return;
                }

                // Browser native TTS via Web Speech API
                if (uiData.type === "speak") {
                    console.log(`[${receiveTime.toFixed(0)}ms] 🔊 TTS: "${uiData.text.substring(0, 50)}..."`);
                    try {
                        if (!window.speechSynthesis) {
                            console.error("❌ speechSynthesis not available in this browser");
                            return;
                        }

                        const utterance = new SpeechSynthesisUtterance(uiData.text);
                        utterance.rate = 1;
                        utterance.pitch = 1;

                        utterance.onstart = () => {
                            console.log(`[${performance.now().toFixed(0)}ms] 🎙️ TTS started`);
                        };

                        utterance.onend = () => {
                            const endTime = performance.now();
                            console.log(`[${endTime.toFixed(0)}ms] 🎙️ TTS ended (grace period: 2s)`);
                            lastTtsEndTime = endTime;  // Start grace period to block mic echo
                        };

                        utterance.onerror = (event) => {
                            console.error(`❌ TTS Error: ${event.error}`);
                        };

                        console.log(`[${performance.now().toFixed(0)}ms] 📢 Calling speechSynthesis.speak()`);
                        window.speechSynthesis.speak(utterance);
                        console.log(`[${performance.now().toFixed(0)}ms] ✅ speechSynthesis.speak() called`);
                    } catch (err) {
                        console.error(`❌ TTS Exception: ${err.message}`);
                    }
                    return;
                }

                // Force HUD to update instantly
                updateHUD();

            } catch (err) {
                console.error("⚠️ [UI Parser Error]:", err);
            }
            return; 
        }

        // 2. AUDIO PLANE: Handle binary audio blobs natively
        try {
            const arrayBuffer = await event.data.arrayBuffer();
            const audioBuffer = await playbackCtx.decodeAudioData(arrayBuffer);
            
            const source = playbackCtx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(playbackCtx.destination);
            
            // Overlapping prevention
            if (nextStartTime < playbackCtx.currentTime) {
                nextStartTime = playbackCtx.currentTime;
            }
            source.start(nextStartTime);
            nextStartTime += audioBuffer.duration;
            
        } catch (err) {
            console.error("⚠️ [Audio Playback Error]:", err);
        }
    };

    ws.onclose = () => {
        console.log('🔴 [Network] Disconnected.');
        ws = null;
    };
    
    ws.onerror = (err) => {
        console.error('⚠️ [Network Error]:', err);
    };
}


// ---------------------------------------------------------
// Audio Capture & VAD Processing
// ---------------------------------------------------------
async function startMicrophone() {
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const source = audioContext.createMediaStreamSource(mediaStream);
        
        processor = audioContext.createScriptProcessor(2048, 1, 1);
        
        let lastVadTime = 0;
        let lastTtsEndTime = 0;
        const TTS_GRACE_PERIOD = 2000;  // Wait 2 seconds after TTS ends before accepting mic input

        processor.onaudioprocess = (e) => {
            const float32Array = e.inputBuffer.getChannelData(0);
            connectWebSocket();

            if (vad.process(float32Array)) {
                // Half-duplex: skip capture while ANY TTS utterance is playing or cooling down
                // Use speechSynthesis.speaking to detect if ANY queued utterance is active
                const now = performance.now();
                if (window.speechSynthesis.speaking || (now - lastTtsEndTime < TTS_GRACE_PERIOD)) {
                    return;
                }

                if (now - lastVadTime > 500) {
                    console.log(`[${now.toFixed(0)}ms] 🎤 VAD triggered, sending audio`);
                    lastVadTime = now;
                }

                const int16Array = new Int16Array(float32Array.length);
                for (let i = 0; i < float32Array.length; i++) {
                    let s = Math.max(-1, Math.min(1, float32Array[i]));
                    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }

                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(int16Array.buffer);
                }
            }
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
        
        logMessage('🎤 Microphone Active. Listening for VAD...');
        if(connectBtn) connectBtn.disabled = true;
        if(disconnectBtn) disconnectBtn.disabled = false;

    } catch (err) {
        console.error("⚠️ Microphone access denied:", err);
        logMessage('⚠️ Error: Microphone access denied.');
    }
}

function stopMicrophone() {
    if (processor) {
        processor.disconnect();
        processor = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
}

// ---------------------------------------------------------
// HUD State Synchronization
// ---------------------------------------------------------
if(connectBtn) {
    connectBtn.onclick = () => {
        if (playbackCtx.state === 'suspended') {
            playbackCtx.resume();
        }
        startMicrophone();
    };
}

if(disconnectBtn) {
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
}

async function updateHUD() {
    try {
        const response = await fetch(`${BACKEND_URL}/state`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Server error');
        }
        const state = await response.json();
        
        const locEl = document.getElementById('loc');
        const healthEl = document.getElementById('health');
        const credEl = document.getElementById('credits');
        
        if(locEl) locEl.innerText = state.location;
        if(healthEl) healthEl.innerText = state.health + "%";
        if(credEl) credEl.innerText = state.credits;
        
        // LLM-driven puzzles arrive over the WebSocket as <terminal> messages,
        // not via the DB. The poller only knows about DB-backed active_puzzle, so
        // it may only OPEN the overlay — never auto-hide one it doesn't track,
        // or it would instantly close a websocket puzzle. Dismissal is handled by
        // the SUBMIT and CLOSE TERMINAL buttons.
        const puzzleOverlay = document.getElementById('puzzle-overlay');
        if (puzzleOverlay && state.puzzle) {
            puzzleOverlay.style.display = 'block';
            document.getElementById('puzzle-desc').innerText = state.puzzle;
        }
    } catch (err) {
        console.warn("⚠️ [HUD] Sync Failed:", err.message);
    }
}

// Background poller (runs every 3 seconds)
setInterval(updateHUD, 3000);