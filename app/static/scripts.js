function switchTab(pid) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.getElementById('tab-' + pid).classList.add('active');
    document.getElementById('content-' + pid).classList.add('active');
    updateStatus(pid);
    updateLiveSnapshot(pid);

    // save the active tab
    localStorage.setItem("activeTab", pid);
}

function updateStatus(pid) {
    fetch('/status/' + pid)
        .then(r => r.json())
        .then(data => {

            const s = document.getElementById('status-text-' + pid);
            if (data.is_online) {
                s.innerHTML = data.is_printing
                    ? '<span class="rec">● RECORDING</span>'
                    : '● STANDBY';
            } else {
                s.innerHTML = 'Offline';
            }

            document.getElementById('progress-text-' + pid).innerText = data.progress + '%';
            document.getElementById('progress-fill-' + pid).style.width = data.progress + '%';

            const smart = document.getElementById('smart-info-' + pid);
            smart.style.display = (data.is_printing && data.mode === 'time') ? 'flex' : 'none';

            if (data.interval)
                document.getElementById('interval-val-' + pid).innerText = data.interval + 's';

            document.getElementById('log-box-' + pid).innerHTML =
                data.logs.map(l => `<div style="border-bottom:1px solid #1e293b">${l}</div>`).join('');

            document.getElementById('remaining-' + pid).innerText = formatTime(data.remaining);
        });
}

function openVid(pid, file) {
    document.getElementById('player').src = '/video_file/' + pid + '/' + file;
    document.getElementById('dl-btn').href = '/video_file/' + pid + '/' + file;
    document.getElementById('modal').style.display = 'flex';
    document.getElementById('player').play();
}

function closeVid() {
    document.getElementById('modal').style.display = 'none';
    document.getElementById('player').pause();
}

function formatTime(value) {
    if (value === null || value === undefined || value === "Unknown") {
        return "--";
    }

    const seconds = value;
    if (isNaN(seconds) || (seconds < 0) || (seconds === 0)) {
        return "--";
    }

    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);

    const hh = h.toString().padStart(2, '0');
    const mm = m.toString().padStart(2, '0');
    const ss = s.toString().padStart(2, '0');

    return `${hh}:${mm}:${ss}`;
}

function updateLiveSnapshot(pid) {
    const img = document.getElementById("live-" + pid);
    if (!img) return;

    // Add a timestamp to avoid the browser cache
    img.src = `/live_snap/${pid}?t=${Date.now()}`;
}

function initGallery(pid) {
    let page = 1;
    let loading = false;
    const gallery = document.getElementById("gallery-" + pid);
    const marker = document.getElementById("load-marker-" + pid);

    async function loadPage() {
        if (loading) return;
        loading = true;

        const r = await fetch(`/timelapse_list/${pid}?page=${page}`);
        const data = await r.json();
        console.log('page of printer id:', pid, page)

        data.videos.forEach(vid => {
            console.log('video load for printer id:', pid)
            const el = document.createElement("div");
            el.className = "vid-item";
            el.onclick = () => openVid(pid, vid);
            el.innerHTML = `
                <img src="/thumb/${pid}/${vid}.jpg" class="vid-thumb">
                <div class="vid-name">${vid}</div>
                <a href="/delete/${pid}/${vid}" class="del-btn"
                    onclick="event.stopPropagation(); return confirm('Delete?')">DEL</a>
            `;
            gallery.appendChild(el);
        });

        loading = false;

        if (data.has_more) {
            page++;
        } else {
            observer.disconnect();
        }
    }

    // Load the first item of the gallery
    loadPage();

    // Load the next item of the gallery at scroll
    const observer = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
            loadPage();
            console.log('observer load a new page', pid, page)
        }
    });

    observer.observe(marker);
}

// Update for active printer tab
setInterval(() => {
    //const printers = document.querySelectorAll(".tab-btn");
    //for (var i = 0; i < printers.length - 1; i++){
    //    const pid = printers[i].id.replace("tab-", "");
    //    updateStatus(pid);
    //    updateLiveSnapshot(pid);
    //}
    const actual_tab = localStorage.getItem("activeTab");

    updateStatus(actual_tab);
    updateLiveSnapshot(actual_tab);
}, 2000);

document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem("activeTab");
    const printers = document.querySelectorAll(".tab-btn");
    const firstpid = printers[0].id.replace("tab-", "")
    console.log('Load HTML page')

    // Init gallery for each printers
    for (var i = 0; i < printers.length - 1; i++){
        const pid = printers[i].id.replace("tab-", "");
        console.log('printer id:', pid)
        initGallery(pid);
    }
    
    // Restore last tab selected
    if (saved) {
        switchTab(saved);
    } else {
        // activate the first tab by default
        if (firstpid) {
            switchTab(firstpid);
        }
    }
});