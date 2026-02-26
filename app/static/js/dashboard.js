// ==========================================
// GLOBAL UTILITIES
// ==========================================

/**
 * Toggles between the raw 8-channel EEG waveform view and the AI prediction bar chart.
 */
function toggleEegView(view) {
    document.getElementById('raw-view-container').classList.toggle('d-none', view !== 'raw');
    document.getElementById('pred-view-container').classList.toggle('d-none', view === 'raw');
}

/**
 * Real-time client-side search filter for the subject management table.
 */
function filterSubjects() {
    const query = document.getElementById('subject-search').value.toLowerCase();
    const rows = document.querySelectorAll('#subject-list-body tr');
    
    rows.forEach(row => {
        const rowText = row.innerText.toLowerCase();
        row.style.display = rowText.includes(query) ? '' : 'none';
    });
}

/**
 * Generates a high-resolution timestamp (including deciseconds) 
 * to give the UI a highly responsive, "live" telemetry feel.
 */
function getLiveTimestamp() {
    const now = new Date();
    return now.getHours().toString().padStart(2, '0') + ":" +
           now.getMinutes().toString().padStart(2, '0') + ":" +
           now.getSeconds().toString().padStart(2, '0') + "." +
           Math.floor(now.getMilliseconds() / 100); 
}

// ==========================================
// ADMIN: SUBJECT MANAGEMENT
// ==========================================

async function loadSubjects() {
    const token = localStorage.getItem('bci_token');
    try {
        const response = await fetch('/api/admin/subjects', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const subjects = await response.json();
        const body = document.getElementById('subject-list-body');
        if (!body) return;

        body.innerHTML = subjects.map(s => `
            <tr>
                <td><span class="badge bg-dark">${s.username}</span></td>
                <td>${s.nickname || '---'}</td>
                <td>${s.age} | ${s.sex}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-info py-0 fw-bold" 
                        onclick="setActiveSubject('${s.username}', '${s.nickname || 'Unknown'}', '${s.age}', '${s.sex}')">
                        SELECT
                    </button>
                    <button class="btn btn-sm btn-outline-danger py-0 ms-1" onclick="deleteSubject('${s.username}')">DEL</button>
                </td>
            </tr>`).join('');
    } catch (e) { console.error("Error loading subjects:", e); }
}

async function setActiveSubject(sid, nick, age, sex) {
    const token = localStorage.getItem('bci_token');
    
    try {
        const response = await fetch(`/api/admin/set-active-subject/${sid}`, { 
            method: 'POST', 
            headers: { 'Authorization': `Bearer ${token}` } 
        });

        if (response.ok) {
            // 1. Update Top UI Bar Data
            document.getElementById('display-id').innerText = sid;
            document.getElementById('display-nick').innerText = nick;
            document.getElementById('display-age').innerText = age;
            document.getElementById('display-sex').innerText = sex;
            document.getElementById('subject-meta').classList.remove('d-none');
            
            // 2. Visual Feedback
            document.getElementById('active-subject-badge').classList.replace('bg-dark', 'bg-success');

            // 3. Success Notification
            Toastify({
                text: `Subject Active: ${nick}`,
                duration: 3000,
                gravity: "top", position: "right", 
                backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)",
                stopOnFocus: true, 
            }).showToast();

            // Clear search filter
            const searchBox = document.getElementById('subject-search');
            if (searchBox) {
                searchBox.value = "";
                filterSubjects();
            }
        }
    } catch (e) {
        Toastify({ text: "Error connecting to server", backgroundColor: "#ff5f6d" }).showToast();
    }
}

async function addNewSubject() {
    const nick = document.getElementById('sub-nick').value;
    const ageInput = document.getElementById('sub-age');
    const age = ageInput.value;
    const sex = document.getElementById('sub-sex').value;
    const token = localStorage.getItem('bci_token');

    if (!age || age < 0 || age > 120) {
        Toastify({
            text: "Please enter a valid age!", duration: 3000,
            gravity: "top", position: "center", style: { background: "#ff5f6d" }
        }).showToast();
        return;
    }

    const url = `/api/admin/create-subject?nickname=${encodeURIComponent(nick)}&age=${age}&sex=${sex}`;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const data = await response.json();
            Toastify({
                text: `Registered: ${nick || data.subject_id}`, duration: 3000,
                gravity: "top", position: "right",
                style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
            }).showToast();

            document.getElementById('sub-nick').value = "";
            ageInput.value = "";
            loadSubjects(); 
        } else {
            Toastify({ text: "Database error: Registration failed.", style: { background: "#e74c3c" } }).showToast();
        }
    } catch (e) { 
        Toastify({ text: "Network error. Check connection.", style: { background: "#e74c3c" } }).showToast();
    }
}

async function deleteSubject(sid) {
    if (!confirm(`Permanently delete subject ${sid}?`)) return;
    
    const token = localStorage.getItem('bci_token');
    try {
        const response = await fetch(`/api/admin/subjects/${sid}`, { 
            method: 'DELETE', 
            headers: { 'Authorization': `Bearer ${token}` } 
        });

        if (response.ok) {
            Toastify({ text: `Subject ${sid} Removed`, backgroundColor: "#333" }).showToast();
            loadSubjects(); 
        } else {
            const err = await response.json();
            alert("Delete failed: " + err.detail);
        }
    } catch (e) { console.error("Network error during delete:", e); }
}

// ==========================================
// REAL-TIME VISUALIZATION ENGINE
// ==========================================



document.addEventListener("DOMContentLoaded", function() {
    const token = localStorage.getItem('bci_token');
    if (!token) { window.location.href = '/login'; return; }
    const authHeaders = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

    // --- 1. Initialize Plotly.js Charts ---
    
    // Raw EEG Waveform Chart
    const eegDiv = document.getElementById('eegChart');
    const channelColors = ['#FF5733', '#33FF57', '#3357FF', '#FF33F5', '#33FFF5', '#F5FF33', '#FF8C33', '#8C33FF'];
    const verticalOffsets = [700, 500, 300, 100, -100, -300, -500, -700];
    
    let eegTraces = channelColors.map((c, i) => ({ 
        y: Array(60).fill(verticalOffsets[i]), 
        type: 'scatter', mode: 'lines', line: {color: c, width: 1.5}, hoverinfo: 'none'
    }));
    
    Plotly.newPlot(eegDiv, eegTraces, { 
        margin: {t:10, b:10, l:30, r:10}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        xaxis:{showgrid:false, showticklabels:false}, yaxis:{range:[-1000, 1000], gridcolor:'#444'}, showlegend:false 
    }, {displayModeBar:false, responsive:true});



    // AI Emotion Probability Bar Chart (8 AffectNet-HQ emotions)
    const emotions = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise'];
    Plotly.newPlot('probChart', [{ 
        x: emotions, y: Array(8).fill(0), type: 'bar', 
        marker: {color: ['#d93025', '#a83232', '#8C33FF', '#000', '#33FF57', '#888', '#3357FF', '#FF8C33']} 
    }], { 
        margin: {t:20, b:40, l:40, r:20}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        yaxis:{range:[0,1], gridcolor:'#444', font:{color:'#fff'}}, xaxis:{font:{color:'#fff'}} 
    }, {displayModeBar:false});

    // Psychological Metrics History Chart (Valence, Arousal, Stress)
    let metricHistory = { v: Array(40).fill(0), a: Array(40).fill(0), s: Array(40).fill(0) };
    let metricTraces = [{y: metricHistory.v, name: 'Valence'}, {y: metricHistory.a, name: 'Arousal'}, {y: metricHistory.s, name: 'Stress'}];
    Plotly.newPlot('metricsChart', metricTraces, { 
        margin: {t:10, b:10, l:30, r:10}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        xaxis:{display:false}, yaxis:{range:[-1.1,1.1], gridcolor:'#444'}, showlegend:false 
    }, {displayModeBar:false});

    // --- 2. Main Polling Loop ---
    function updateDashboard() {
        fetch('/api/live', { headers: authHeaders })
        .then(res => res.json())
        .then(data => {
            const ts = getLiveTimestamp(); // Use the global utility function

            // Check if a session was activated remotely
            if (data.session && data.session.subject_id && document.getElementById('display-id').innerText === "STANDBY") {
                document.getElementById('display-id').innerText = data.session.subject_id;
            }

            // Determine active sensors based on backend data
            const eegActive = data.eeg.raw_sample && data.eeg.raw_sample[0] !== 0;
            const faceActive = data.face && data.face.emotion && data.face.emotion !== "None";

            document.getElementById('eeg-overlay').classList.toggle('d-none', eegActive);
            document.getElementById('face-overlay').classList.toggle('d-none', faceActive);

            // --- Update Face UI ---
            if (faceActive) {
                document.getElementById('face-val').innerText = data.face.emotion.toUpperCase();
                document.getElementById('face-conf').innerText = `CONF: ${(data.face.conf * 100).toFixed(1)}%`;
                
                const faceHB = document.getElementById('face-heartbeat');
                faceHB.innerText = `LIVE: ${ts}`;
                faceHB.classList.add('blink'); 
                
                document.getElementById('face-val').style.color = (data.face.conf > 0.6) ? "#008b8b" : "#b8860b";
            } else {
                document.getElementById('face-val').innerText = "INIT...";
                const faceHB = document.getElementById('face-heartbeat');
                if (faceHB) faceHB.classList.remove('blink');
            }

            // --- Update EEG UI ---
            if (eegActive) {
                document.getElementById('eeg-emotion-label').innerText = data.eeg.emotion.toUpperCase();
                
                const eegHB = document.getElementById('eeg-heartbeat');
                eegHB.innerText = `LIVE: ${ts}`;
                eegHB.classList.add('blink');

                // Shift raw waveforms left and push new sample (restyle is highly optimized)
                let updatedY = eegTraces.map((t, i) => { 
                    t.y.push(data.eeg.raw_sample[i] + verticalOffsets[i]); 
                    t.y.shift(); 
                    return t.y; 
                });
                Plotly.restyle(eegDiv, { y: updatedY });
                
                // Update Bar Chart
                Plotly.restyle('probChart', { y: [data.eeg.probs] });
                
                // Update Metrics History
                const m = data.eeg.metrics;
                metricHistory.v.push(m.valence); metricHistory.v.shift();
                metricHistory.a.push(m.arousal); metricHistory.a.shift();
                metricHistory.s.push(m.stress); metricHistory.s.shift();
                Plotly.restyle('metricsChart', { y: [metricHistory.v, metricHistory.a, metricHistory.s] });

                document.getElementById('val-num').innerText = m.valence.toFixed(2);
                document.getElementById('aro-num').innerText = (m.arousal * 100).toFixed(0) + "%";
                document.getElementById('str-num').innerText = (m.stress * 100).toFixed(0) + "%";
            } else {
                document.getElementById('eeg-emotion-label').innerText = "OFFLINE";
                const eegHB = document.getElementById('eeg-heartbeat');
                if (eegHB) eegHB.classList.remove('blink');
            }

            // --- Update Neural Fusion UI ---
            const fActiveUI = document.getElementById('fusion-active-ui');
            const fWaitingUI = document.getElementById('fusion-waiting-ui');
            const statusBadge = document.getElementById('match-status');
            const fusionHB = document.getElementById('fusion-heartbeat');
            
            if (eegActive || faceActive) {
                fActiveUI.classList.remove('d-none'); 
                fWaitingUI.classList.add('d-none');
                document.getElementById('fusion-val').innerText = data.fusion.emotion.toUpperCase();
                
                // --- UPDATED SYNC LOGIC ---
                // The timer and blink effect now only run if BOTH sensors are synced
                if (eegActive && faceActive) {
                    fusionHB.innerText = `SYNC: ${ts}`;
                    fusionHB.classList.add('blink');
                    fusionHB.classList.replace('bg-dark', 'bg-danger'); // Red for active sync
                } else {
                    fusionHB.innerText = `AWAITING EEG`;
                    fusionHB.classList.remove('blink');
                    fusionHB.classList.replace('bg-danger', 'bg-dark'); // Dark/Grey for standby
                }
                
                // Badge Logic for status
                if (eegActive && faceActive) {
                    statusBadge.innerText = data.fusion.match ? "SENSORS AGREE" : "DISSENT DETECTED";
                    statusBadge.className = `badge ${data.fusion.match ? 'bg-success' : 'bg-danger'} px-3 py-2 mt-2`;
                } else if (faceActive) {
                    statusBadge.innerText = "CAMERA ONLY MODE";
                    statusBadge.className = "badge bg-info text-dark px-3 py-2 mt-2";
                } else {
                    statusBadge.innerText = "EEG ONLY MODE";
                    statusBadge.className = "badge bg-warning text-dark px-3 py-2 mt-2";
                }
            } else { 
                fActiveUI.classList.add('d-none'); 
                fWaitingUI.classList.remove('d-none'); 
            }
        });
    }

    // Initialize UI and start the telemetry polling loop at ~6.6Hz
    loadSubjects(); 
    setInterval(updateDashboard, 150);
});