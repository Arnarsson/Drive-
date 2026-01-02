const $ = id => document.getElementById(id);

let locations = [];
let selectedOrigin = null;
let selectedDest = null;

function todayISO() {
  const d = new Date();
  return d.toISOString().split('T')[0];
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch {}
  if (!res.ok) {
    const msg = (data && data.detail) ? data.detail : text || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function setStatus(msg, isError = false) {
  const el = $("status");
  el.textContent = msg || "";
  el.className = isError ? "danger" : "success";
}

function escapeHtml(str) {
  return (str || "").replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

function formatAddress(loc) {
  return loc.postal_code ? `${loc.address}, ${loc.postal_code}` : loc.address;
}

// Render location buttons
function renderLocations() {
  const originContainer = $("origin-locations");
  const destContainer = $("dest-locations");
  originContainer.innerHTML = "";
  destContainer.innerHTML = "";

  locations.forEach(loc => {
    const addr = formatAddress(loc);

    // Origin button
    const originBtn = document.createElement("span");
    originBtn.className = `loc-btn${loc.is_home ? " home" : ""}${selectedOrigin === loc.id ? " selected" : ""}`;
    originBtn.textContent = loc.name;
    originBtn.title = addr;
    originBtn.onclick = () => {
      selectedOrigin = selectedOrigin === loc.id ? null : loc.id;
      $("origin").value = selectedOrigin ? addr : "";
      renderLocations();
    };
    originContainer.appendChild(originBtn);

    // Destination button (skip home for destinations usually)
    const destBtn = document.createElement("span");
    destBtn.className = `loc-btn${loc.is_home ? " home" : ""}${selectedDest === loc.id ? " selected" : ""}`;
    destBtn.textContent = loc.name;
    destBtn.title = addr;
    destBtn.onclick = () => {
      selectedDest = selectedDest === loc.id ? null : loc.id;
      $("destination").value = selectedDest ? addr : "";
      renderLocations();
    };
    destContainer.appendChild(destBtn);
  });
}

async function loadLocations() {
  try {
    locations = await fetchJSON("/api/locations");
    renderLocations();

    // Auto-select home as default origin
    const home = locations.find(l => l.is_home);
    if (home && !$("origin").value) {
      selectedOrigin = home.id;
      $("origin").value = formatAddress(home);
      renderLocations();
    }
  } catch (e) {
    console.error("Failed to load locations:", e);
  }
}

async function loadSummary() {
  const year = parseInt($("year").value, 10);
  try {
    const s = await fetchJSON(`/api/summary?year=${year}`);
    $("summary-container").innerHTML = `
      <div class="summary-box">
        <h3>${year} Oversigt</h3>
        <div class="summary-stats">
          <div class="stat">
            <div class="stat-value">${s.trip_count}</div>
            <div class="stat-label">Ture</div>
          </div>
          <div class="stat">
            <div class="stat-value">${s.total_km.toLocaleString("da-DK")} km</div>
            <div class="stat-label">Total kørsel</div>
          </div>
          <div class="stat">
            <div class="stat-value">${s.reimbursement_dkk.toLocaleString("da-DK", {minimumFractionDigits: 2})} kr</div>
            <div class="stat-label">Godtgørelse (${s.rate_high} kr/km)</div>
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    console.error("Failed to load summary:", e);
  }
}

async function loadTrips() {
  const year = parseInt($("year").value, 10);
  const trips = await fetchJSON(`/api/trips?year=${year}`);

  const tbody = $("tbody");
  tbody.innerHTML = "";

  if (trips.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted" style="text-align:center">Ingen ture registreret</td></tr>';
    return;
  }

  trips.forEach(t => {
    const tr = document.createElement("tr");
    const oneWay = t.distance_one_way_km || (t.round_trip ? t.distance_km / 2 : t.distance_km);
    tr.innerHTML = `
      <td>${t.trip_date}</td>
      <td>${escapeHtml(t.purpose)}</td>
      <td>
        <div>${escapeHtml(t.origin)}</div>
        <div class="muted">&rarr; ${escapeHtml(t.destination)}
          ${t.round_trip ? '<span class="badge round-trip">tur/retur</span>' : ''}
        </div>
      </td>
      <td style="text-align:right">
        <strong>${t.distance_km.toFixed(1)}</strong>
        <div class="muted" style="font-size:0.8rem">${oneWay.toFixed(1)} x ${t.round_trip ? '2' : '1'}</div>
      </td>
      <td><button class="danger small" data-id="${t.id}">Slet</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async e => {
      if (!confirm("Slet denne tur?")) return;
      await fetchJSON(`/api/trips/${t.id}`, { method: "DELETE" });
      refresh();
    });
    tbody.appendChild(tr);
  });
}

async function refresh() {
  setStatus("");
  try {
    await Promise.all([loadTrips(), loadSummary()]);
  } catch (e) {
    setStatus(e.message, true);
  }
}

async function addTrip() {
  setStatus("");
  const btn = $("btn_add");
  btn.disabled = true;
  btn.textContent = "Beregner rute...";

  const payload = {
    trip_date: $("trip_date").value,
    purpose: $("purpose").value,
    origin: $("origin").value,
    destination: $("destination").value,
    round_trip: $("round_trip").checked,
    travel_mode: "DRIVE"
  };

  try {
    const trip = await fetchJSON("/api/trips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setStatus(`Gemt: ${trip.distance_km.toFixed(1)} km`);

    // Clear form (keep origin as it's usually home)
    $("purpose").value = "";
    $("destination").value = "";
    selectedDest = null;
    renderLocations();

    await refresh();
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Beregn & gem tur";
  }
}

function exportCSV() {
  const year = parseInt($("year").value, 10);
  window.location.href = `/api/export.csv?year=${year}`;
}

// Init
window.addEventListener("DOMContentLoaded", async () => {
  $("trip_date").value = todayISO();
  $("year").value = new Date().getFullYear();

  $("btn_add").addEventListener("click", addTrip);
  $("btn_refresh").addEventListener("click", refresh);
  $("btn_export").addEventListener("click", exportCSV);

  // Clear selection when typing in input
  $("origin").addEventListener("input", () => { selectedOrigin = null; renderLocations(); });
  $("destination").addEventListener("input", () => { selectedDest = null; renderLocations(); });

  await loadLocations();
  await refresh();
});
