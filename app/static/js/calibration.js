/**
 * BCI Calibration System - Power Baseline Edition.
 * 30 Seconds per image | 90 Seconds total session time.
 */
const CalibrationSystem = {
    isActive: false,
    progress: 0,
    // Calculation: 90 seconds * 30 frames per second = 2700 points
    targetPoints: 2700, 
    
    lastSwitchTime: 0,
    currentImgIndex: 0,
    switchInterval: 30000, // Exactly 30 seconds
    
    imagePool: { focus: [], neutral: [], relax: [] }, 
    
    elements: {
        guide: () => document.getElementById('calibration-guide'),
        bar: () => document.getElementById('calib-progress'),
        timer: () => document.getElementById('calib-timer'),
        status: () => document.getElementById('calib-status-text'),
        image: () => document.getElementById('calib-image-display'),
        activeId: () => document.getElementById('display-id')
    },

    init: async function() {
        const token = localStorage.getItem('bci_token');
        try {
            const response = await fetch('/api/calibration-images', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                // 1 image from each category
                this.imagePool = data;
                this.preloadImages(); 
            }
        } catch (e) { console.warn("Image fetch failed", e); }
    },

    preloadImages: function() {
        ['focus', 'neutral', 'relax'].forEach(phase => {
            if(this.imagePool[phase]) {
                this.imagePool[phase].forEach(src => { (new Image()).src = src; });
            }
        });
    },

    start: function() {
        if (this.isActive) return;
        const activeSubject = this.elements.activeId().innerText;
        if (activeSubject === "STANDBY") {
            Toastify({ text: "Please select a subject first!", backgroundColor: "#d93025" }).showToast();
            return;
        }

        this.isActive = true;
        this.progress = 0;
        this.currentImgIndex = 0; // Starts with the first image in each phase
        this.lastSwitchTime = Date.now();
        
        this.elements.guide().classList.remove('d-none');
        this.updateStimuli(0);
        this.updateUI("Initiating 90s Power Baseline...", "#17a2b8", 0);
    },

    processFrame: function(faceEmotion, faceConf) {
        if (!this.isActive) return;

        // THRESHOLD: 20% (0.20)
        if (faceEmotion && faceEmotion.toLowerCase() === "neutral" && faceConf >= 0.20) {
            this.progress++;
            const percent = (this.progress / this.targetPoints) * 100;
            this.updateStimuli(percent);

            const bar = this.elements.bar();
            if (bar) {
                bar.classList.remove('bg-danger');
                bar.classList.add('bg-info');
            }
        } else {
            // No progress drain, just a pause
            const percent = (this.progress / this.targetPoints) * 100;
            this.updateUI("Paused: Keep Face Neutral", "#dc3545", percent);
            const bar = this.elements.bar();
            if (bar) bar.classList.add('bg-danger');
        }

        if (this.progress >= this.targetPoints) { this.complete(); }
    },

    updateStimuli: function(percent) {
        const calibImg = this.elements.image();
        if (!calibImg) return;

        const now = Date.now();
        let phase = percent < 33.3 ? 'focus' : (percent < 66.6 ? 'neutral' : 'relax');
        let label = percent < 33.3 ? "Phase 1: Focus" : (percent < 66.6 ? "Phase 2: Empty Mind" : "Phase 3: Relax");

        const pool = this.imagePool[phase];
        if (pool && pool.length > 0) {
            const targetImage = pool[0]; 
            
            if (calibImg.getAttribute('src') !== targetImage) {
                calibImg.style.opacity = 0;
                setTimeout(() => {
                    calibImg.src = targetImage;
                    calibImg.style.opacity = 1;
                }, 400);
            }
        }

        const remaining = Math.max(0, Math.floor(30 - (now - this.lastSwitchTime) / 1000));
        this.updateUI(`${label} (${remaining}s)`, "#28a745", percent);
        
        // Reset timer when phase shifts to keep the 30s countdown accurate per image
        if (now - this.lastSwitchTime >= this.switchInterval) {
            this.lastSwitchTime = now;
        }
    },

    updateUI: function(text, color, percent) {
        const timer = this.elements.timer();
        if (timer) { timer.innerText = text; timer.style.color = color; }
        const bar = this.elements.bar();
        if (bar) bar.style.width = percent + "%";
    },

    complete: function() {
        this.isActive = false;
        this.elements.guide().classList.add('d-none');
        if (confirm("Calibration Complete. Save 90s Baseline?")) {
            fetch('/api/calibrate-done', { 
                method: 'POST', 
                headers: { 
                    'Authorization': `Bearer ${localStorage.getItem('bci_token')}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ subject_id: this.elements.activeId().innerText, apply_update: true })
            }).then(() => Toastify({ text: "Baseline Locked", backgroundColor: "#6f42c1" }).showToast());
        }
    },

    stop: function() { this.isActive = false; this.elements.guide().classList.add('d-none'); }
};

document.addEventListener('DOMContentLoaded', () => CalibrationSystem.init());