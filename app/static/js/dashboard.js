// GLOBAL UTILITIES & SECURITY

function getAuthHeaders() {
    const token = localStorage.getItem('bci_token');
    return {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    };
}

function toggleEegView(view) {
    document.getElementById('raw-view-container').classList.toggle('d-none', view !== 'raw');
    document.getElementById('pred-view-container').classList.toggle('d-none', view === 'raw');
}

function filterSubjects() {
    const query = document.getElementById('subject-search').value.toLowerCase();
    const rows = document.querySelectorAll('#subject-list-body tr');
    rows.forEach(row => {
        const rowText = row.innerText.toLowerCase();
        row.style.display = rowText.includes(query) ? '' : 'none';
    });
}

function getLiveTimestamp() {
    const now = new Date();
    return now.getHours().toString().padStart(2, '0') + ":" +
           now.getMinutes().toString().padStart(2, '0') + ":" +
           now.getSeconds().toString().padStart(2, '0') + "." +
           Math.floor(now.getMilliseconds() / 100); 
}

// ADMIN: SUBJECT MANAGEMENT

async function loadSubjects() {
    try {
        const response = await fetch('/api/admin/subjects', { headers: getAuthHeaders() });
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
    try {
        const response = await fetch(`/api/admin/set-active-subject/${sid}`, { 
            method: 'POST', 
            headers: getAuthHeaders() 
        });

        if (response.ok) {
            document.getElementById('display-id').innerText = sid;
            document.getElementById('display-nick').innerText = nick;
            document.getElementById('display-age').innerText = age;
            document.getElementById('display-sex').innerText = sex;
            document.getElementById('subject-meta').classList.remove('d-none');
            document.getElementById('active-subject-badge').classList.replace('bg-dark', 'bg-success');

            Toastify({
                text: `Subject Active: ${nick}`, duration: 3000, gravity: "top", position: "right", 
                backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)"
            }).showToast();

            const searchBox = document.getElementById('subject-search');
            if (searchBox) { searchBox.value = ""; filterSubjects(); }
        }
    } catch (e) { Toastify({ text: "Error connecting to server", backgroundColor: "#ff5f6d" }).showToast(); }
}

async function addNewSubject() {
    const nick = document.getElementById('sub-nick').value;
    const ageInput = document.getElementById('sub-age');
    const age = ageInput.value;
    const sex = document.getElementById('sub-sex').value;

    if (!age || age < 0 || age > 120) {
        Toastify({ text: "Please enter a valid age!", duration: 3000, backgroundColor: "#ff5f6d" }).showToast();
        return;
    }

    const url = `/api/admin/create-subject?nickname=${encodeURIComponent(nick)}&age=${age}&sex=${sex}`;
    try {
        const response = await fetch(url, { method: 'POST', headers: getAuthHeaders() });
        if (response.ok) {
            const data = await response.json();
            Toastify({ text: `Registered: ${nick || data.subject_id}`, backgroundColor: "#00b09b" }).showToast();
            document.getElementById('sub-nick').value = "";
            ageInput.value = "";
            loadSubjects(); 
        } else {
            Toastify({ text: "Registration failed.", backgroundColor: "#e74c3c" }).showToast();
        }
    } catch (e) { Toastify({ text: "Network error.", backgroundColor: "#e74c3c" }).showToast(); }
}

async function deleteSubject(sid) {
    if (!confirm(`Permanently delete subject ${sid}?`)) return;
    try {
        const response = await fetch(`/api/admin/subjects/${sid}`, { method: 'DELETE', headers: getAuthHeaders() });
        if (response.ok) {
            Toastify({ text: `Subject ${sid} Removed`, backgroundColor: "#333" }).showToast();
            loadSubjects(); 
        } else {
            alert("Delete failed.");
        }
    } catch (e) { console.error("Network error during delete:", e); }
}

// REAL-TIME VISUALIZATION ENGINE

let eegDiv, eegTraces, verticalOffsets, metricHistory;

function initCharts() {
    eegDiv = document.getElementById('eegChart');
    const channelColors = ['#FF5733', '#33FF57', '#3357FF', '#FF33F5', '#33FFF5', '#F5FF33', '#FF8C33', '#8C33FF'];
    verticalOffsets = [700, 500, 300, 100, -100, -300, -500, -700];
    
    eegTraces = channelColors.map((c, i) => ({ 
        y: Array(250).fill(verticalOffsets[i]), 
        type: 'scatter', mode: 'lines', line: {color: c, width: 1.5}, hoverinfo: 'none'
    }));
    
    Plotly.newPlot(eegDiv, eegTraces, { 
        margin: {t:10, b:10, l:30, r:10}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        xaxis:{showgrid:false, showticklabels:false}, yaxis:{range:[-1000, 1000], gridcolor:'#444'}, showlegend:false 
    }, {displayModeBar:false, responsive:true});

    const emotions = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise'];
    Plotly.newPlot('probChart', [{ 
        x: emotions, y: Array(8).fill(0), type: 'bar', 
        marker: {color: ['#d93025', '#a83232', '#8C33FF', '#000', '#33FF57', '#888', '#3357FF', '#FF8C33']} 
    }], { 
        margin: {t:20, b:40, l:40, r:20}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        yaxis:{range:[0,1], gridcolor:'#444', font:{color:'#fff'}}, xaxis:{font:{color:'#fff'}} 
    }, {displayModeBar:false});

    metricHistory = { v: Array(40).fill(0), a: Array(40).fill(0), s: Array(40).fill(0) };
    let metricTraces = [{y: metricHistory.v, name: 'Valence'}, {y: metricHistory.a, name: 'Arousal'}, {y: metricHistory.s, name: 'Stress'}];
    Plotly.newPlot('metricsChart', metricTraces, { 
        margin: {t:10, b:10, l:30, r:10}, paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 
        xaxis:{display:false}, yaxis:{range:[-1.1,1.1], gridcolor:'#444'}, showlegend:false 
    }, {displayModeBar:false});
}

let faceDropCounter = 0;
let cachedFaceEmotion = "INIT...";
let cachedFaceConf = 0.0;

function updateDashboard() {
    const headers = getAuthHeaders();
    if (!headers) { window.location.href = '/login'; return; }

    fetch('/api/live', { headers: headers })
    .then(res => {
        if (res.status === 401 || res.status === 403) {
            localStorage.removeItem('bci_token');
            window.location.href = '/login';
            throw new Error("Session Expired");
        }
        return res.json();
    })
    .then(data => {
        const ts = getLiveTimestamp();

        if (data.session && data.session.subject_id && document.getElementById('display-id').innerText === "STANDBY") {
            document.getElementById('display-id').innerText = data.session.subject_id;
        }

        const eegActive = data.eeg && data.eeg.emotion !== "OFFLINE" && data.eeg.emotion !== "None";
        let faceActive = false;

        if (data.face && data.face.emotion && data.face.emotion !== "None") {
            faceDropCounter = 0;
            cachedFaceEmotion = data.face.emotion.toUpperCase();
            cachedFaceConf = data.face.conf;
            faceActive = true;
        } else {
            faceDropCounter++;
            faceActive = (faceDropCounter < 6);
        }

        if (typeof CalibrationSystem !== 'undefined' && CalibrationSystem.isActive) {
            CalibrationSystem.processFrame(data.face.emotion, data.face.conf);
        }

        document.getElementById('eeg-overlay').classList.toggle('d-none', eegActive);
        document.getElementById('face-overlay').classList.toggle('d-none', faceActive);

        // Update Face UI
        if (faceActive && cachedFaceEmotion !== "INIT...") {
            document.getElementById('face-val').innerText = cachedFaceEmotion;
            document.getElementById('face-conf').innerText = `CONF: ${(cachedFaceConf * 100).toFixed(1)}%`;
            const faceHB = document.getElementById('face-heartbeat');
            faceHB.innerText = `LIVE: ${ts}`;
            faceHB.classList.add('blink');
            document.getElementById('face-val').style.color = (cachedFaceConf > 0.6) ? "#008b8b" : "#b8860b";
        }

        // Update EEG UI
        if (eegActive) {
            document.getElementById('eeg-emotion-label').innerText = data.eeg.emotion.toUpperCase();
            const eegHB = document.getElementById('eeg-heartbeat');
            eegHB.innerText = `LIVE: ${ts}`;
            eegHB.classList.add('blink');

            let updatedY = eegTraces.map((t, i) => { 
                t.y.push(data.eeg.raw_sample[i] + verticalOffsets[i]); 
                t.y.shift(); 
                return t.y; 
            });
            Plotly.restyle(eegDiv, { y: updatedY });
            Plotly.restyle('probChart', { y: [data.eeg.probs] });

            const m = data.eeg.metrics;
            metricHistory.v.push(m.valence); metricHistory.v.shift();
            metricHistory.a.push(m.arousal); metricHistory.a.shift();
            metricHistory.s.push(m.stress); metricHistory.s.shift();
            Plotly.restyle('metricsChart', { y: [metricHistory.v, metricHistory.a, metricHistory.s] });

            document.getElementById('val-num').innerText = m.valence.toFixed(2);
            document.getElementById('aro-num').innerText = (m.arousal * 100).toFixed(0) + "%";
            document.getElementById('str-num').innerText = (m.stress * 100).toFixed(0) + "%";
        }

        // FUSION UI LOGIC
        const fActiveUI = document.getElementById('fusion-active-ui');
        const fWaitingUI = document.getElementById('fusion-waiting-ui');
        const statusBadge = document.getElementById('match-status');
        const fusionHB = document.getElementById('fusion-heartbeat');
        
        if (eegActive || faceActive) {
            fActiveUI.classList.remove('d-none'); 
            fWaitingUI.classList.add('d-none');
            document.getElementById('fusion-val').innerText = data.fusion.emotion.toUpperCase();
            
            if (eegActive && faceActive) {
                fusionHB.innerText = `SYNC: ${ts}`;
                fusionHB.classList.add('blink');
                fusionHB.classList.replace('bg-dark', 'bg-danger'); 
                
                // --- DYNAMIC BADGE COLORS ---
                if (data.fusion.status === "Synced") {
                    statusBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i> SYNCED';
                    statusBadge.className = "badge bg-success text-white px-3 py-2 mt-2 shadow-sm";
                } else if (data.fusion.status === "Dissonance Detected") {
                    statusBadge.innerHTML = '<i class="bi bi-exclamation-octagon me-1"></i> DISSENT DETECTED';
                    statusBadge.className = "badge bg-danger text-white px-3 py-2 mt-2 shadow-sm";
                } else {
                    // Fallback for "Mixed" or low confidence
                    statusBadge.innerText = data.fusion.status.toUpperCase();
                    statusBadge.className = "badge bg-warning text-dark px-3 py-2 mt-2 shadow-sm";
                }
                
            } else if (faceActive) {
                fusionHB.innerText = `AWAITING EEG`;
                fusionHB.classList.remove('blink');
                fusionHB.classList.replace('bg-danger', 'bg-dark'); 
                statusBadge.innerText = "CAMERA ONLY MODE";
                statusBadge.className = "badge bg-info text-dark px-3 py-2 mt-2 shadow-sm";
            } else {
                statusBadge.innerText = "EEG ONLY MODE";
                statusBadge.className = "badge bg-warning text-dark px-3 py-2 mt-2 shadow-sm";
            }
        } else { 
            fActiveUI.classList.add('d-none'); 
            fWaitingUI.classList.remove('d-none'); 
        }
    })
    .catch(err => console.debug("Polling..."))
    .finally(() => {
        setTimeout(updateDashboard, 150); // Recursive safe-polling
    });
}

document.addEventListener("DOMContentLoaded", function() {
    const token = localStorage.getItem('bci_token');
    if (!token) { window.location.href = '/login'; return; }
    
    const videoImg = document.querySelector('.video-container img');
    if (videoImg) {
        videoImg.src = `/face_stream?token=${token}`;
    }

    initCharts();
    loadSubjects(); 
    updateDashboard(); // Start loop
});