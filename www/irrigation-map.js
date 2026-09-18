/**
 * Irrigation Map Card
 * Shows a satellite view of the garden with animated zone overlays.
 *
 * Config options in lovelace:
 *   type: custom:irrigation-map-card
 *   lat: 39.7817   (optional, defaults shown)
 *   lng: -89.6501
 *   zoom: 19
 *
 * The Google Maps API key is injected by the deployment pipeline — do NOT add
 * api_key to the card YAML config.
 *
 * Zone polygon positions are estimated — adjust the ZONE_DEFS below to match
 * your actual garden layout. Coordinates are x,y on a 600×380 image.
 */

// ─── Google Maps API key — replaced by pipeline on deployment ────────────────
const GOOGLE_MAPS_API_KEY = '#{google_maps_api_key}';
// ─────────────────────────────────────────────────────────────────────────────

// ─── Tweak these polygon points to match your real zone boundaries ────────────
// Each entry: points as "x1,y1 x2,y2 ..." in a 600×380 coordinate space
// Sprinkler positions are GPS-derived at zoom 19, centred on 39.7817, -89.6501
// Update card config lat/lng to match: lat: 39.7817  lng: -89.6501
const DEFAULT_ZONES = [
  {
    entity: 'valve.wt_11w_zone_2',
    name: 'Zone 2',
    color: '#e53935',   // red
    glow: 'rgba(229,57,53,0.55)',
    // Right-side drip bed along east boundary
    points: '532,215 592,215 592,240 532,240',
    sprinklers: [[572, 227]],
  },
  {
    entity: 'valve.wt_11w_zone_1',
    name: 'Zone 1',
    color: '#1e88e5',   // blue
    glow: 'rgba(30,136,229,0.55)',
    // Centre-right lawn/bed — three sprinkler heads
    points: '430,238 556,238 558,283 428,286',
    sprinklers: [[531, 263], [479, 257], [453, 257]],
  },
  {
    entity: 'valve.wt_11w_zone_3',
    name: 'Zone 3',
    color: '#fdd835',   // yellow
    glow: 'rgba(253,216,53,0.55)',
    // Main lawn — left hedge strip and centre reach
    points: '15,98 450,188 435,240 305,252 15,142',
    sprinklers: [[28, 117], [345, 239], [438, 202]],
  },
];
// ─────────────────────────────────────────────────────────────────────────────

class IrrigationMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = {};
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 5; }

  _state(entityId) {
    return this._hass?.states?.[entityId]?.state ?? null;
  }

  _toggle(entityId) {
    if (!this._hass) return;
    const svc = this._state(entityId) === 'open' ? 'close_valve' : 'open_valve';
    this._hass.callService('valve', svc, { entity_id: entityId });
  }

  _mapUrl() {
    // Use key from card config if provided, otherwise fall back to pipeline-injected constant
    const key = this._config.api_key
      || (GOOGLE_MAPS_API_KEY.startsWith('#{') ? null : GOOGLE_MAPS_API_KEY);
    if (!key) return null;
    const lat = this._config.lat ?? 39.7817;
    const lng = this._config.lng ?? -89.6501;
    const zoom = this._config.zoom ?? 19;
    return `https://maps.googleapis.com/maps/api/staticmap?center=${lat},${lng}&zoom=${zoom}&size=600x380&maptype=satellite&key=${key}`;
  }

  _sprinkler(cx, cy, active, color) {
    const outer = active ? color : '#455a64';
    const inner = active ? '#fff' : '#90a4ae';
    let h = '';
    h += `<g class="${active ? 'hpulse' : ''}" transform="translate(${cx},${cy})">`;
    h += `<circle r="7" fill="${outer}"/>`;
    h += `<circle r="3.5" fill="${inner}"/>`;
    h += '</g>';
    if (active) {
      const stroke = color;
      h += `<circle cx="${cx}" cy="${cy}" r="5" fill="none" stroke="${stroke}" stroke-width="2.5" class="r1"/>`;
      h += `<circle cx="${cx}" cy="${cy}" r="5" fill="none" stroke="${stroke}" stroke-width="2" class="r2"/>`;
      h += `<circle cx="${cx}" cy="${cy}" r="5" fill="none" stroke="${stroke}" stroke-width="1" class="r3"/>`;
    }
    return h;
  }

  _render() {
    if (!this._hass) return;

    const zones = this._config.zones
      ? this._config.zones.map((z, i) => ({ ...DEFAULT_ZONES[i], ...z }))
      : DEFAULT_ZONES;

    const states = zones.map(z => this._state(z.entity) === 'open');
    const anyOn = states.some(Boolean);
    const mapUrl = this._mapUrl();

    // ── Styles ──────────────────────────────────────────────────────────────
    const css = `
      :host { display: block; }
      .card {
        background: var(--ha-card-background, #1c1c1e);
        border-radius: 12px;
        overflow: hidden;
        box-shadow: var(--ha-card-box-shadow, none);
      }
      .header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 13px 16px 4px;
        color: var(--primary-text-color, #e1e1e1);
        font-size: 1.05em; font-weight: 600;
      }
      .badge {
        font-size: .72em; font-weight: 500; padding: 3px 11px;
        border-radius: 12px;
        background: ${anyOn ? 'rgba(100,181,246,0.15)' : 'rgba(255,255,255,0.08)'};
        color: ${anyOn ? '#64b5f6' : 'var(--secondary-text-color,#9e9e9e)'};
        border: 1px solid ${anyOn ? 'rgba(100,181,246,0.35)' : 'transparent'};
      }
      .wrap {
        padding: 8px 10px 12px;
        position: relative;
      }
      .map-bg {
        width: 100%; display: block;
        border-radius: 8px;
        background: #1a2e1a;
        min-height: 200px;
      }
      .svg-overlay {
        position: absolute;
        top: 8px; left: 10px;
        width: calc(100% - 20px);
        height: calc(100% - 20px);
        border-radius: 8px;
        overflow: hidden;
      }

      /* Zone polygons */
      .zone { cursor: pointer; }
      .zone:hover polygon.zbg { filter: brightness(1.25); }
      .zone polygon.zbg { transition: filter .2s; }

      /* Labels */
      .zlabel {
        font-size: 14px; font-weight: 700; pointer-events: none;
        text-anchor: middle; dominant-baseline: middle;
        filter: drop-shadow(0 1px 2px rgba(0,0,0,.8));
      }
      .zstatus {
        font-size: 10px; pointer-events: none;
        text-anchor: middle; dominant-baseline: middle;
        filter: drop-shadow(0 1px 2px rgba(0,0,0,.9));
      }

      /* Water rings */
      @keyframes ripple  { 0% { r:5; opacity:.9; } 100% { r:42; opacity:0; } }
      @keyframes ripple2 { 0% { r:5; opacity:.7; } 100% { r:32; opacity:0; } }
      @keyframes ripple3 { 0% { r:5; opacity:.5; } 100% { r:20; opacity:0; } }
      .r1 { animation: ripple  2s ease-out 0.0s infinite; }
      .r2 { animation: ripple2 2s ease-out 0.7s infinite; }
      .r3 { animation: ripple3 2s ease-out 1.4s infinite; }

      @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.3; } }
      .hpulse { animation: pulse 1.1s ease-in-out infinite; }

      @keyframes glow { 0%,100% { opacity:.45; } 50% { opacity:1; } }
      .glow { animation: glow 1.5s ease-in-out infinite; }

      /* Legend */
      .legend {
        display: flex; gap: 14px; flex-wrap: wrap;
        padding: 4px 10px 10px;
      }
      .legend-item {
        display: flex; align-items: center; gap: 6px;
        font-size: .78em;
        color: var(--secondary-text-color, #9e9e9e);
      }
      .legend-dot {
        width: 11px; height: 11px; border-radius: 50%;
        flex-shrink: 0;
      }
    `;

    // ── Build SVG ────────────────────────────────────────────────────────────
    let svg = '<svg viewBox="0 0 600 380" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:100%;">';

    // No satellite image? Draw a fallback garden
    if (!mapUrl) {
      svg += '<rect x="0" y="0" width="600" height="380" fill="#162516"/>';
      svg += '<text x="300" y="340" style="font-size:11px;fill:rgba(255,255,255,0.35);text-anchor:middle;">Satellite view requires API key (set by pipeline)</text>';
    }

    // Zone polygons
    zones.forEach((z, i) => {
      const on = states[i];
      const fillOpacity = on ? '0.55' : '0.30';
      const pts = (this._config.zones?.[i]?.points) || z.points;

      svg += `<g class="zone" data-zone="${i}">`;

      // Fill
      svg += `<polygon class="zbg" points="${pts}" fill="${z.color}" fill-opacity="${fillOpacity}" stroke="${z.color}" stroke-width="1.5" stroke-opacity="0.7"/>`;

      // Active glow border
      if (on) {
        svg += `<polygon points="${pts}" fill="none" stroke="${z.color}" stroke-width="3" opacity="0.8" class="glow"/>`;
      }

      // Compute centroid for label
      const coords = pts.trim().split(/\s+/).map(p => p.split(',').map(Number));
      const cx = coords.reduce((s, p) => s + p[0], 0) / coords.length;
      const cy = coords.reduce((s, p) => s + p[1], 0) / coords.length;

      svg += `<text x="${cx}" y="${cy - 10}" class="zlabel" fill="${on ? z.color : '#fff'}">${z.name}</text>`;
      svg += `<text x="${cx}" y="${cy + 10}" class="zstatus" fill="${on ? z.color : 'rgba(255,255,255,0.65)'}">${on ? '● Running' : 'Tap to toggle'}</text>`;

      svg += '</g>';
    });

    // Sprinkler heads
    zones.forEach((z, i) => {
      const on = states[i];
      const heads = (this._config.zones?.[i]?.sprinklers) || z.sprinklers;
      heads.forEach(([cx, cy]) => {
        svg += this._sprinkler(cx, cy, on, z.color);
      });
    });

    svg += '</svg>';

    // ── Build legend ─────────────────────────────────────────────────────────
    const legend = zones.map((z, i) =>
      `<div class="legend-item">
         <div class="legend-dot" style="background:${z.color};opacity:${states[i] ? '1' : '0.65'};"></div>
         <span>${z.name}${states[i] ? ' ●' : ''}</span>
       </div>`
    ).join('');

    // ── Assemble ─────────────────────────────────────────────────────────────
    let mapHtml;
    if (mapUrl) {
      mapHtml = `<img class="map-bg" src="${mapUrl}" alt="Garden satellite view" onerror="this.style.minHeight='220px'"/>`;
    } else {
      mapHtml = `<div class="map-bg" style="height:220px;"></div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>${css}</style>
      <div class="card">
        <div class="header">
          <span>&#127807; Garden Irrigation</span>
          <span class="badge">${anyOn ? '&#128167; Running' : 'Idle'}</span>
        </div>
        <div class="wrap">
          ${mapHtml}
          <div class="svg-overlay">${svg}</div>
        </div>
        <div class="legend">${legend}</div>
      </div>
    `;

    // Attach click listeners
    const self = this;
    this.shadowRoot.querySelectorAll('.zone').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.getAttribute('data-zone'));
        self._toggle(zones[idx].entity);
      });
    });
  }
}

customElements.define('irrigation-map-card', IrrigationMapCard);
