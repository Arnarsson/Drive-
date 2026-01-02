function $(id) { return document.getElementById(id); }

function todayISO() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
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

function setStatus(msg) { $("status").textContent = msg || ""; }
function setError(msg) { $("error").textContent = msg || ""; }

async function refresh() {
  setError("");
  const year = parseInt($("year").value, 10);
  const trips = await fetchJSON(`/api/trips?year=${year}`);

  const tbody = $("tbody");
  tbody.innerHTML = "";

  trips.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${t.trip_date}</td>
      <td>${escapeHtml(t.purpose)}</td>
      <td><div><strong>${escapeHtml(t.origin)}</strong></div>
          <div class="muted">-> ${escapeHtml(t.destination)} ${t.round_trip ? "(round trip)" : ""}</div></td>
      <td>${t.distance_km.toFixed(3)}</td>
      <td><button data-id="${t.id}">Delete</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async (e) => {
      const id = e.target.getAttribute("data-id");
      await fetchJSON(`/api/trips/${id}`, { method: "DELETE" });
      await refresh();
    });
    tbody.appendChild(tr);
  });

  const s = await fetchJSON(`/api/summary?year=${year}`);
  $("summary").textContent = `Trips: ${s.trip_count} | Total km: ${s.total_km.toFixed(3)} | Est. reimbursement: ${s.reimbursement_estimate_dkk?.toFixed(2)} DKK`;
}

function escapeHtml(str) {
  return (str || "").replace(/[&<>"']/g, (m) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[m]));
}

async function addTrip() {
  setError("");
  setStatus("Calculating route distance...");

  const payload = {
    trip_date: $("trip_date").value,
    purpose: $("purpose").value,
    origin: $("origin").value,
    destination: $("destination").value,
    round_trip: $("round_trip").checked,
    travel_mode: $("travel_mode").value
  };

  try {
    await fetchJSON("/api/trips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setStatus("Saved!");
    await refresh();
  } catch (e) {
    setError(e.message);
    setStatus("");
  }
}

function exportCSV() {
  const year = parseInt($("year").value, 10);
  window.location.href = `/api/export.csv?year=${year}`;
}

window.addEventListener("DOMContentLoaded", () => {
  $("trip_date").value = todayISO();
  $("year").value = new Date().getFullYear();

  $("btn_add").addEventListener("click", addTrip);
  $("btn_refresh").addEventListener("click", refresh);
  $("btn_export").addEventListener("click", exportCSV);

  refresh().catch(err => setError(err.message));
});
