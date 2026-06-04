let ws;
let audioContext;
let mediaStream;
let processor;

//Initialize the playback audio context
const playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
let nextStartTime = 0; 

const SAMPLE_RATE = 16000;
const CHUNK_SIZE_MS = 20;
const BUFFER_SIZE = Math.floor(SAMPLE_RATE * (CHUNK_SIZE_MS / 1000));
const vad = new VoiceActivityDetector()

const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const logDiv = document.getElementById('log');

function logMessage(msg) {
    logDiv.innerHTML += `> ${msg}<br>`;
    logDiv.scrollTop = logDiv.scrollHeight;
}

async function startMicrophone() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        logMessage('Microphone access granted.');

        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
        
        if (playbackCtx.state === 'suspended') {
            await playbackCtx.resume();
        }

        const source = audioContext.createMediaStreamSource(mediaStream);
        processor = audioContext.createScriptProcessor(4096, 1, 1);
        let audioBuffer = [];

        processor.onaudioprocess = (e) => {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            for (let i = 0; i < inputData.length; i++) {
                let s = Math.max(-1, Math.min(1, inputData[i]));
                let int16 = s < 0 ? s * 0x8000 : s * 0x7FFF;
                audioBuffer.push(int16);
            }

            while (audioBuffer.length >= BUFFER_SIZE) {
                const chunk = audioBuffer.splice(0, BUFFER_SIZE);
                const int16Array = new Int16Array(chunk);
                
                if (vad.hasSpeech(int16Array)){
                    ws.send(int16Array.buffer);
                }
            }
        };

        source.connect(processor);
        processor.connect(audioContext.destination);

    } catch (err) {
        logMessage(`⚠️ Microphone Error: ${err.message}`);
    }
}

function stopMicrophone() {
    if (processor) {
        processor.disconnect();
        processor = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    logMessage('🔇 Microphone deactivated.');
}

connectBtn.onclick = () => {
    ws = new WebSocket('ws://127.0.0.1:8000/stream');
    ws.binaryType = 'arraybuffer';

    ws.onopen = async () => {
        logMessage('🟢 Connected to Event Broker.');
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        await startMicrophone();
    };

    ws.onmessage = async (event) => {
        let arrayBuffer;

        if (event.data instanceof ArrayBuffer) {
            arrayBuffer = event.data;
        } else if (event.data instanceof Blob) {
            arrayBuffer = await event.data.arrayBuffer();
        } else {
            console.log("💬 [Text Message]:", event.data);
            return; 
        }

        try {
            if (playbackCtx.state === 'suspended') {
                await playbackCtx.resume();
            }

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
                
                logMessage(`🔵 Played AI Audio Response.`);
            }, (error) => {
                console.error("❌ [Decode Error] Browser failed to decode the MP3:", error);
            });
        } catch (err) {
            console.error("❌ [Fatal Error] Web Audio API crashed during decode:", err);
        }
    };

    ws.onclose = () => {
        logMessage('🔴 Disconnected from Event Broker.');
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
        stopMicrophone();
    };

    ws.onerror = () => {
        logMessage('⚠️ WebSocket Error.');
    };
};

disconnectBtn.onclick = () => {
    if (ws) ws.close();
};