// Secure Vault Updating 
function updateVault() {
    const token = localStorage.getItem('bci_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    fetch('/api/history', {
        method: 'GET',
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        }
    })
    .then(res => {
        if (res.status === 401 || res.status === 403) {
            localStorage.removeItem('bci_token');
            window.location.href = '/login';
            throw new Error("Session expired."); 
        }
        return res.json();
    })
    .then(data => {
        const tbody = document.getElementById('log-body');
        if (!tbody) return; 
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">Awaiting stabilized sensor data...</td></tr>';
            return;
        }
        
        let newHtml = '';
        data.forEach(row => {
            let statusBadge = '';
            const currentStatus = row.status || 'Unknown'; 
            const currentEmotion = row.fusion || 'None';
            
            // Calculate confidence percentage for the UI meter
            const confPercent = Math.round((row.confidence || 0) * 100);

            // REFINED STATUS LOGIC 
            if (currentStatus === 'Synced' || currentStatus === 'STABLE') {
                statusBadge = '<span class="badge bg-success text-white px-3 py-2 rounded-pill shadow-sm"><i class="bi bi-shield-check me-1"></i> SYNCED</span>';
            } 
            else if (currentStatus === 'Dissonance' || currentEmotion.includes('MASKED')) {
                statusBadge = '<span class="badge bg-danger text-white px-3 py-2 rounded-pill shadow-sm"><i class="bi bi-eye-slash me-1"></i> DISSONANCE</span>';
            } 
            else {
                statusBadge = `<span class="badge bg-warning text-dark px-3 py-2 rounded-pill shadow-sm">${currentStatus.toUpperCase()}</span>`;
            }

            // Professional UI formatting
            const eegEmo = row.details.eeg.emotion.replace('...', '');
            const faceEmo = row.details.face.emotion;

            // Confidence Meter HTML component
            const confidenceMeter = `
                <div class="mt-2" style="max-width: 100px;">
                    <div class="progress" style="height: 4px; background-color: rgba(0,0,0,0.05);">
                        <div class="progress-bar ${confPercent > 70 ? 'bg-info' : 'bg-secondary'}" 
                             role="progressbar" style="width: ${confPercent}%"></div>
                    </div>
                    <div style="font-size: 0.6rem;" class="text-muted fw-bold mt-1">${confPercent}% CERTAINTY</div>
                </div>
            `;

            newHtml += `
                <tr>
                    <td class="text-secondary small align-middle" style="font-family: 'Courier New', monospace;">${row.time}</td>
                    <td class="align-middle">
                        ${statusBadge}
                        <div class="mt-2 small fw-bold text-dark text-uppercase ls-1">${row.fusion}</div>
                        ${confidenceMeter}
                    </td>
                    <td class="align-middle">
                         <span class="badge bg-light text-dark border px-2 py-1">${eegEmo}</span>
                         <div class="text-muted mt-1" style="font-size: 0.65rem; font-weight: 600;">NEURAL TRUTH</div>
                    </td>
                    <td class="align-middle">
                         <span class="badge bg-light text-dark border px-2 py-1">${faceEmo}</span>
                         <div class="text-muted mt-1" style="font-size: 0.65rem; font-weight: 600;">OPTICAL MASK</div>
                    </td>
                </tr>
            `;
        });
        
        tbody.innerHTML = newHtml;
    })
    .catch(err => console.error("Vault fetch error:", err));
}

// Secure CSV Export 
async function downloadCSV() {
    const token = localStorage.getItem('bci_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    try {
        Toastify({
            text: "Decrypting and compiling CSV...",
            duration: 2000,
            gravity: "top",
            style: { background: "#17a2b8" }
        }).showToast();

        const response = await fetch('/api/export', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        if (!response.ok) {
            throw new Error("Unauthorized or server error");
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `bci_session_${Math.floor(Date.now() / 1000)}.csv`;
        document.body.appendChild(a);
        a.click();
        
        a.remove();
        window.URL.revokeObjectURL(url);

    } catch (err) {
        console.error("CSV Download failed:", err);
        Toastify({
            text: "Export Failed: Secure Vault Error",
            duration: 3000,
            style: { background: "#d93025" }
        }).showToast();
    }
}

// Initialization 
document.addEventListener("DOMContentLoaded", function() {
    updateVault(); 
    setInterval(updateVault, 2000);
});