/**
 * Mileage Tracker - Spreadsheet-style UI
 * Danish tax documentation (kørselsgodtgørelse)
 */

// =============================================================================
// State Management
// =============================================================================

const state = {
  locations: [],
  trips: [],
  filteredTrips: [],
  selectedYear: new Date().getFullYear(),
  selectedMonth: 'all', // 'all' or 1-12
  selectedOrigin: null,
  selectedDest: null,
  searchQuery: '',
  activeFilter: 'all',
  isLoading: false,
  deleteTargetId: null,
  editingTripId: null,
};

// =============================================================================
// Utility Functions
// =============================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function todayISO() {
  return new Date().toISOString().split('T')[0];
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function formatNumber(num, decimals = 1) {
  return num.toLocaleString('da-DK', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function formatAddress(loc) {
  return loc.postal_code ? `${loc.address}, ${loc.postal_code}` : loc.address;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('da-DK', { day: 'numeric', month: 'short' });
}

function formatDateFull(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('da-DK', { day: 'numeric', month: 'short', year: 'numeric' });
}

function debounce(fn, delay) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

// =============================================================================
// API Functions
// =============================================================================

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (e) {
    // Not JSON
  }
  if (!res.ok) {
    const msg = data?.detail || text || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(message, type = 'info', duration = 4000) {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icons = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  };

  toast.innerHTML = `
    <div class="toast-icon">${icons[type]}</div>
    <div class="toast-content">
      <div class="toast-message">${escapeHtml(message)}</div>
    </div>
    <button class="toast-close" aria-label="Luk">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>
  `;

  container.appendChild(toast);

  const closeBtn = toast.querySelector('.toast-close');
  const dismiss = () => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 200);
  };

  closeBtn.addEventListener('click', dismiss);
  setTimeout(dismiss, duration);

  $('#live-region').textContent = message;
}

// =============================================================================
// Modal Dialogs
// =============================================================================

function openTripModal(tripId = null) {
  state.editingTripId = tripId;
  const backdrop = $('#trip-modal-backdrop');
  const title = $('#trip-modal-title');
  const btn = $('#btn_add');

  if (tripId) {
    // Edit mode
    const trip = state.trips.find(t => t.id === tripId);
    if (!trip) return;

    title.textContent = 'Rediger tur';
    btn.querySelector('.btn-text').textContent = 'Gem ændringer';

    $('#trip_date').value = trip.trip_date;
    $('#purpose').value = trip.purpose;
    $('#origin').value = trip.origin;
    $('#destination').value = trip.destination;
    $('#round_trip').checked = trip.round_trip;
  } else {
    // Add mode
    title.textContent = 'Tilføj tur';
    btn.querySelector('.btn-text').textContent = 'Gem tur';

    $('#trip_date').value = todayISO();
    $('#purpose').value = '';
    $('#destination').value = '';
    $('#round_trip').checked = true;

    // Auto-select home as origin
    const home = state.locations.find(l => l.is_home);
    if (home) {
      state.selectedOrigin = home.id;
      $('#origin').value = formatAddress(home);
    } else {
      $('#origin').value = '';
    }
  }

  renderLocations();
  backdrop.classList.remove('hidden');
  backdrop.setAttribute('aria-hidden', 'false');
  $('#purpose').focus();
}

function closeTripModal() {
  const backdrop = $('#trip-modal-backdrop');
  backdrop.classList.add('hidden');
  backdrop.setAttribute('aria-hidden', 'true');
  state.editingTripId = null;
  state.selectedOrigin = null;
  state.selectedDest = null;
  hideDistancePreview();
}

function showDeleteModal(tripId) {
  state.deleteTargetId = tripId;
  const backdrop = $('#delete-modal-backdrop');
  backdrop.classList.remove('hidden');
  backdrop.setAttribute('aria-hidden', 'false');
  $('#delete-confirm').focus();
}

function hideDeleteModal() {
  const backdrop = $('#delete-modal-backdrop');
  backdrop.classList.add('hidden');
  backdrop.setAttribute('aria-hidden', 'true');
  state.deleteTargetId = null;
}

async function confirmDelete() {
  if (!state.deleteTargetId) return;

  try {
    await fetchJSON(`/api/trips/${state.deleteTargetId}`, { method: 'DELETE' });
    showToast('Tur slettet', 'success');
    hideDeleteModal();
    await refresh();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// =============================================================================
// Distance Preview
// =============================================================================

let previewTimeout = null;

function showDistancePreview() {
  $('#distance-preview').classList.remove('hidden');
}

function hideDistancePreview() {
  $('#distance-preview').classList.add('hidden');
  $('#preview-distance').textContent = '--';
}

async function updateDistancePreview() {
  const origin = $('#origin').value.trim();
  const destination = $('#destination').value.trim();
  const roundTrip = $('#round_trip').checked;

  if (origin.length < 3 || destination.length < 3) {
    hideDistancePreview();
    return;
  }

  showDistancePreview();
  $('#preview-distance').textContent = 'Beregner...';

  try {
    const data = await fetchJSON('/api/preview-distance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, destination, round_trip: roundTrip }),
    });

    $('#preview-distance').textContent = `${formatNumber(data.total_km)} km${roundTrip ? ' (tur/retur)' : ''}`;
  } catch (e) {
    $('#preview-distance').textContent = 'Kunne ikke beregne';
  }
}

const debouncedPreview = debounce(updateDistancePreview, 800);

// =============================================================================
// Year & Month Navigation
// =============================================================================

function updateYearDisplay() {
  $('#year-display').textContent = state.selectedYear;
  $('#current-year-label').textContent = state.selectedYear;
}

function selectYear(year) {
  state.selectedYear = year;
  updateYearDisplay();
  refresh();
}

function prevYear() {
  selectYear(state.selectedYear - 1);
}

function nextYear() {
  selectYear(state.selectedYear + 1);
}

function selectMonth(month) {
  state.selectedMonth = month;

  // Update tab UI
  $$('.sheet-tab').forEach(tab => {
    const tabMonth = tab.dataset.month;
    tab.classList.toggle('active', tabMonth === String(month));
  });

  applyFilters();
  renderTrips();
}

function updateMonthTabIndicators() {
  // Calculate trip counts per month
  const monthCounts = {};
  state.trips.forEach(t => {
    const month = new Date(t.trip_date).getMonth() + 1;
    monthCounts[month] = (monthCounts[month] || 0) + 1;
  });

  // Update tab indicators
  $$('.sheet-tab').forEach(tab => {
    const month = tab.dataset.month;
    if (month === 'all') {
      // Total count for "Hele året"
      const total = state.trips.length;
      tab.classList.toggle('has-data', total > 0);
      // Show count badge
      const existingBadge = tab.querySelector('.tab-count');
      if (existingBadge) existingBadge.remove();
      if (total > 0) {
        const badge = document.createElement('span');
        badge.className = 'tab-count';
        badge.textContent = total;
        tab.appendChild(badge);
      }
    } else {
      const count = monthCounts[parseInt(month, 10)] || 0;
      tab.classList.toggle('has-data', count > 0);
    }
  });
}

// =============================================================================
// Location Chips
// =============================================================================

function renderLocations() {
  renderLocationChips('origin-locations', 'origin', true);
  renderLocationChips('dest-locations', 'destination', false);
}

function renderLocationChips(containerId, inputId, isOrigin) {
  const container = $(`#${containerId}`);
  if (!container) return;

  const selectedId = isOrigin ? state.selectedOrigin : state.selectedDest;

  container.innerHTML = state.locations.map(loc => {
    const addr = formatAddress(loc);
    const isSelected = selectedId === loc.id;
    const classes = ['location-chip'];
    if (loc.is_home) classes.push('home');
    if (isSelected) classes.push('selected');

    return `
      <button
        type="button"
        class="${classes.join(' ')}"
        data-id="${loc.id}"
        data-address="${escapeHtml(addr)}"
        title="${escapeHtml(addr)}"
        aria-pressed="${isSelected}"
      >
        ${escapeHtml(loc.name)}
      </button>
    `;
  }).join('');

  // Add click handlers
  container.querySelectorAll('.location-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const id = parseInt(chip.dataset.id, 10);
      const address = chip.dataset.address;
      const input = $(`#${inputId}`);

      if (isOrigin) {
        state.selectedOrigin = state.selectedOrigin === id ? null : id;
        input.value = state.selectedOrigin ? address : '';
      } else {
        state.selectedDest = state.selectedDest === id ? null : id;
        input.value = state.selectedDest ? address : '';
      }

      renderLocations();
      debouncedPreview();
    });
  });
}

// =============================================================================
// Stats Bar
// =============================================================================

// Store yearly summary for rate info
let yearlyRates = { high: 3.94, low: 2.28 };

async function loadSummary() {
  try {
    const s = await fetchJSON(`/api/summary?year=${state.selectedYear}`);
    yearlyRates = { high: s.rate_high, low: s.rate_low };
    updateStatsDisplay();
  } catch (e) {
    console.error('Failed to load summary:', e);
  }
}

function updateStatsDisplay() {
  // Calculate stats from filtered trips (respects month filter)
  const totalKm = state.filteredTrips.reduce((sum, t) => sum + t.distance_km, 0);
  const tripCount = state.filteredTrips.length;

  // Calculate reimbursement using Danish rates
  const threshold = 20000;
  let reimbursement;
  if (totalKm <= threshold) {
    reimbursement = totalKm * yearlyRates.high;
  } else {
    reimbursement = (threshold * yearlyRates.high) + ((totalKm - threshold) * yearlyRates.low);
  }

  $('#stat-trips').textContent = tripCount;
  $('#stat-km').textContent = formatNumber(totalKm);
  $('#stat-amount').textContent = `${formatNumber(reimbursement, 2)} kr`;
  $('#stat-rate').textContent = `${yearlyRates.high} kr/km`;
}

// =============================================================================
// Trips List (Sheet Rows)
// =============================================================================

async function loadTrips() {
  setLoading(true);
  try {
    state.trips = await fetchJSON(`/api/trips?year=${state.selectedYear}`);
    applyFilters();
    renderTrips();
    updateMonthTabIndicators();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    setLoading(false);
  }
}

function applyFilters() {
  let filtered = [...state.trips];

  // Month filter
  if (state.selectedMonth !== 'all') {
    const month = parseInt(state.selectedMonth, 10);
    filtered = filtered.filter(t => {
      const tripMonth = new Date(t.trip_date).getMonth() + 1;
      return tripMonth === month;
    });
  }

  // Search filter
  if (state.searchQuery) {
    const query = state.searchQuery.toLowerCase();
    filtered = filtered.filter(t =>
      t.purpose.toLowerCase().includes(query) ||
      t.origin.toLowerCase().includes(query) ||
      t.destination.toLowerCase().includes(query)
    );
  }

  // Type filter
  if (state.activeFilter === 'round-trip') {
    filtered = filtered.filter(t => t.round_trip);
  } else if (state.activeFilter === 'one-way') {
    filtered = filtered.filter(t => !t.round_trip);
  }

  state.filteredTrips = filtered;
}

function renderTrips() {
  const isEmpty = state.filteredTrips.length === 0;
  const sheetBody = $('#sheet-body');
  const emptyState = $('#empty-state');
  const loadingState = $('#loading-state');

  // Update stats to reflect current filter
  updateStatsDisplay();

  // Toggle states
  emptyState.classList.toggle('hidden', !isEmpty || state.isLoading);
  loadingState.classList.toggle('hidden', !state.isLoading);

  if (isEmpty || state.isLoading) {
    sheetBody.innerHTML = '';
    return;
  }

  sheetBody.innerHTML = state.filteredTrips.map(t => {
    const typeLabel = t.round_trip ? 'Tur/retur' : 'Enkelt';
    // Calculate one-way distance
    const oneWayKm = t.distance_one_way_km || (t.round_trip ? t.distance_km / 2 : t.distance_km);
    // Add long-distance class for trips > 100km total
    const isLongDistance = t.distance_km > 100;
    const rowClasses = ['sheet-row'];
    if (isLongDistance) rowClasses.push('long-distance');

    return `
      <div class="${rowClasses.join(' ')}" data-id="${t.id}">
        <div class="sheet-cell cell-date">${formatDate(t.trip_date)}</div>
        <div class="sheet-cell cell-purpose">${escapeHtml(t.purpose)}</div>
        <div class="sheet-cell cell-from" title="${escapeHtml(t.origin)}">${escapeHtml(t.origin)}</div>
        <div class="sheet-cell cell-to" title="${escapeHtml(t.destination)}">${escapeHtml(t.destination)}</div>
        <div class="sheet-cell cell-km-one">${formatNumber(oneWayKm)}</div>
        <div class="sheet-cell cell-km">${formatNumber(t.distance_km)}</div>
        <div class="sheet-cell cell-type">
          <span class="type-badge ${t.round_trip ? 'round-trip' : 'one-way'}">${typeLabel}</span>
        </div>
        <div class="sheet-cell cell-actions">
          <button class="row-action-btn delete-btn" data-id="${t.id}" title="Slet">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Add delete handlers
  sheetBody.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      showDeleteModal(parseInt(btn.dataset.id, 10));
    });
  });
}

function setLoading(isLoading) {
  state.isLoading = isLoading;
  const loadingState = $('#loading-state');
  loadingState.classList.toggle('hidden', !isLoading);
}

// =============================================================================
// Add/Edit Trip
// =============================================================================

async function handleTripFormSubmit(e) {
  e.preventDefault();

  const btn = $('#btn_add');
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');

  btn.disabled = true;
  btnText.textContent = state.editingTripId ? 'Gemmer...' : 'Beregner rute...';
  spinner?.classList.remove('hidden');

  const tripDate = $('#trip_date').value;
  const purpose = $('#purpose').value;
  const origin = $('#origin').value;
  const destination = $('#destination').value;
  const roundTrip = $('#round_trip').checked;

  try {
    if (state.editingTripId) {
      // Update existing trip (only date and purpose can be changed)
      await fetchJSON(`/api/trips/${state.editingTripId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trip_date: tripDate, purpose }),
      });
      showToast('Tur opdateret', 'success');
    } else {
      // Create new trip
      const trip = await fetchJSON('/api/trips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trip_date: tripDate,
          purpose,
          origin,
          destination,
          round_trip: roundTrip,
          travel_mode: 'DRIVE',
        }),
      });
      showToast(`Gemt: ${formatNumber(trip.distance_km)} km`, 'success');
    }

    closeTripModal();
    await refresh();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btnText.textContent = state.editingTripId ? 'Gem ændringer' : 'Gem tur';
    spinner?.classList.add('hidden');
  }
}

// =============================================================================
// Search & Filter
// =============================================================================

function handleSearch(query) {
  state.searchQuery = query;
  applyFilters();
  renderTrips();
}

function handleFilterClick(filter) {
  state.activeFilter = filter;

  // Update UI
  $$('.filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });

  applyFilters();
  renderTrips();
}

// =============================================================================
// Export CSV
// =============================================================================

function exportCSV() {
  window.location.href = `/api/export.csv?year=${state.selectedYear}`;
}

// =============================================================================
// Data Loading
// =============================================================================

async function loadLocations() {
  try {
    state.locations = await fetchJSON('/api/locations');
  } catch (e) {
    console.error('Failed to load locations:', e);
  }
}

async function refresh() {
  await Promise.all([loadTrips(), loadSummary()]);
}

// =============================================================================
// Calendar Integration
// =============================================================================

function openCalendarModal() {
  const backdrop = $('#calendar-modal-backdrop');
  backdrop.classList.remove('hidden');
  backdrop.setAttribute('aria-hidden', 'false');
  loadCalendarEvents();
}

function closeCalendarModal() {
  const backdrop = $('#calendar-modal-backdrop');
  backdrop.classList.add('hidden');
  backdrop.setAttribute('aria-hidden', 'true');
}

async function loadCalendarEvents() {
  const loading = $('#calendar-loading');
  const empty = $('#calendar-empty');
  const notConnected = $('#calendar-not-connected');
  const eventsContainer = $('#calendar-events');

  // Reset state
  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  notConnected.classList.add('hidden');
  eventsContainer.classList.add('hidden');

  try {
    const events = await fetchJSON('/api/calendar/events');

    loading.classList.add('hidden');

    if (!events || events.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    renderCalendarEvents(events);
    eventsContainer.classList.remove('hidden');
  } catch (e) {
    loading.classList.add('hidden');

    // Check if calendar is not configured
    if (e.message.includes('not configured') || e.message.includes('501')) {
      notConnected.classList.remove('hidden');
    } else {
      showToast(e.message, 'error');
      notConnected.classList.remove('hidden');
    }
  }
}

function renderCalendarEvents(events) {
  const container = $('#calendar-events');
  const monthNames = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

  container.innerHTML = events.map(event => {
    const date = new Date(event.date);
    const day = date.getDate();
    const month = monthNames[date.getMonth()];

    return `
      <div class="calendar-event" data-event='${JSON.stringify(event).replace(/'/g, "&#39;")}'>
        <div class="calendar-event-date">
          <span class="calendar-event-day">${day}</span>
          <span class="calendar-event-month">${month}</span>
        </div>
        <div class="calendar-event-info">
          <div class="calendar-event-title" title="${escapeHtml(event.title)}">${escapeHtml(event.title)}</div>
          <div class="calendar-event-location">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
              <circle cx="12" cy="10" r="3"/>
            </svg>
            <span>${escapeHtml(event.location)}</span>
          </div>
        </div>
        <div class="calendar-event-action">
          <button class="btn-add-event" data-date="${event.date}" data-title="${escapeHtml(event.title)}" data-location="${escapeHtml(event.location)}">
            + Tilføj
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Add click handlers
  container.querySelectorAll('.btn-add-event').forEach(btn => {
    btn.addEventListener('click', () => {
      addTripFromEvent(btn.dataset);
    });
  });
}

function addTripFromEvent(eventData) {
  closeCalendarModal();

  // Open trip modal with pre-filled data
  openTripModal();

  // Pre-fill the form
  $('#trip_date').value = eventData.date;
  $('#purpose').value = eventData.title;
  $('#destination').value = eventData.location;

  // Focus on the origin field since that's what needs to be filled
  $('#origin').focus();

  showToast('Udfyld startadresse og gem turen', 'info');
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

function handleKeyboardShortcuts(e) {
  // Ctrl/Cmd + N: New trip
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
    e.preventDefault();
    openTripModal();
  }

  // Ctrl/Cmd + E: Export
  if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
    e.preventDefault();
    exportCSV();
  }

  // Escape: Close modals
  if (e.key === 'Escape') {
    if (!$('#delete-modal-backdrop').classList.contains('hidden')) {
      hideDeleteModal();
    }
    if (!$('#trip-modal-backdrop').classList.contains('hidden')) {
      closeTripModal();
    }
    if (!$('#calendar-modal-backdrop').classList.contains('hidden')) {
      closeCalendarModal();
    }
  }
}

// =============================================================================
// Event Listeners & Initialization
// =============================================================================

function initEventListeners() {
  // Add trip button (toolbar)
  $('#btn_add_trip')?.addEventListener('click', () => openTripModal());

  // Empty state add button
  $('#empty-add-btn')?.addEventListener('click', () => openTripModal());

  // Trip form
  $('#trip-form')?.addEventListener('submit', handleTripFormSubmit);

  // Trip modal close
  $('#trip-modal-close')?.addEventListener('click', closeTripModal);
  $('#trip-cancel')?.addEventListener('click', closeTripModal);
  $('#trip-modal-backdrop')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeTripModal();
  });

  // Delete modal
  $('#delete-cancel')?.addEventListener('click', hideDeleteModal);
  $('#delete-confirm')?.addEventListener('click', confirmDelete);
  $('#delete-modal-backdrop')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) hideDeleteModal();
  });

  // Year navigation
  $('#prev-year')?.addEventListener('click', prevYear);
  $('#next-year')?.addEventListener('click', nextYear);

  // Month tabs
  $('#month-tabs')?.addEventListener('click', (e) => {
    const tab = e.target.closest('.sheet-tab');
    if (tab && tab.dataset.month) {
      selectMonth(tab.dataset.month);
    }
  });

  // Search
  $('#search-input')?.addEventListener('input', debounce((e) => {
    handleSearch(e.target.value);
  }, 300));

  // Filter buttons
  $$('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => handleFilterClick(btn.dataset.filter));
  });

  // Export
  $('#btn_export')?.addEventListener('click', exportCSV);

  // Refresh
  $('#btn_refresh')?.addEventListener('click', refresh);

  // Calendar modal
  $('#btn_calendar')?.addEventListener('click', openCalendarModal);
  $('#calendar-modal-close')?.addEventListener('click', closeCalendarModal);
  $('#calendar-modal-backdrop')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeCalendarModal();
  });

  // Location input changes (clear selection when typing)
  $('#origin')?.addEventListener('input', () => {
    state.selectedOrigin = null;
    renderLocations();
    debouncedPreview();
  });
  $('#destination')?.addEventListener('input', () => {
    state.selectedDest = null;
    renderLocations();
    debouncedPreview();
  });

  // Round trip toggle updates preview
  $('#round_trip')?.addEventListener('change', debouncedPreview);

  // Keyboard shortcuts
  document.addEventListener('keydown', handleKeyboardShortcuts);
}

// Initialize
window.addEventListener('DOMContentLoaded', async () => {
  initEventListeners();
  await loadLocations();

  // Load all trips first to find the best year to show
  const allTrips = await fetchJSON('/api/trips');

  // Find the most recent year with data, or use current year
  if (allTrips && allTrips.length > 0) {
    const yearsWithData = [...new Set(allTrips.map(t => new Date(t.trip_date).getFullYear()))];
    yearsWithData.sort((a, b) => b - a); // Most recent first
    state.selectedYear = yearsWithData[0];
  }

  updateYearDisplay();
  await refresh();

  // Select "Hele året" tab by default
  selectMonth('all');
});
