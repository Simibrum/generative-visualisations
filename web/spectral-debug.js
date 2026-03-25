(function() {
  let stylesInjected = false;

  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const style = document.createElement('style');
    style.textContent = `
      .spectral-debug {
        position: fixed;
        right: 16px;
        bottom: 16px;
        width: min(260px, calc(100vw - 32px));
        padding: 12px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 12px;
        background: rgba(0, 0, 0, 0.72);
        backdrop-filter: blur(10px);
        color: #fff;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 11px;
        letter-spacing: 0.04em;
        z-index: 20;
        display: none;
        pointer-events: none;
      }
      .spectral-debug.is-visible { display: block; }
      .spectral-debug__title {
        margin-bottom: 10px;
        color: rgba(255, 255, 255, 0.9);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
      }
      .spectral-debug__band + .spectral-debug__band {
        margin-top: 8px;
      }
      .spectral-debug__meta {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 4px;
      }
      .spectral-debug__label {
        color: rgba(255, 255, 255, 0.92);
      }
      .spectral-debug__range {
        color: rgba(255, 255, 255, 0.45);
        font-size: 10px;
      }
      .spectral-debug__value {
        color: rgba(255, 255, 255, 0.68);
        font-variant-numeric: tabular-nums;
      }
      .spectral-debug__meter {
        height: 8px;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.1);
      }
      .spectral-debug__fill {
        width: 0%;
        height: 100%;
        border-radius: inherit;
        box-shadow: 0 0 12px currentColor;
        transition: width 80ms linear;
      }
      .spectral-debug__footer {
        margin-top: 10px;
        color: rgba(255, 255, 255, 0.4);
        font-size: 10px;
      }
    `;
    document.head.appendChild(style);
  }

  function clamp(value) {
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, Math.min(1, value));
  }

  window.createSpectralDebug = function(options) {
    injectStyles();

    const config = options || {};
    const root = document.createElement('div');
    const title = document.createElement('div');
    const bandsEl = document.createElement('div');
    const footer = document.createElement('div');
    const rows = [];

    root.className = 'spectral-debug';
    title.className = 'spectral-debug__title';
    title.textContent = config.title || 'spectral analyser';
    bandsEl.className = 'spectral-debug__bands';
    footer.className = 'spectral-debug__footer';
    footer.textContent = config.footer || 'press S to toggle';
    root.appendChild(title);
    root.appendChild(bandsEl);
    root.appendChild(footer);
    document.body.appendChild(root);
    let visible = false;

    document.addEventListener('keydown', function(event) {
      if (event.repeat) return;
      if ((event.key || '').toLowerCase() !== 's') return;
      visible = !visible;
      root.classList.toggle('is-visible', visible);
    });

    function createRow() {
      const band = document.createElement('div');
      const meta = document.createElement('div');
      const textWrap = document.createElement('div');
      const label = document.createElement('div');
      const range = document.createElement('span');
      const value = document.createElement('div');
      const meter = document.createElement('div');
      const fill = document.createElement('div');

      band.className = 'spectral-debug__band';
      meta.className = 'spectral-debug__meta';
      label.className = 'spectral-debug__label';
      range.className = 'spectral-debug__range';
      value.className = 'spectral-debug__value';
      meter.className = 'spectral-debug__meter';
      fill.className = 'spectral-debug__fill';

      textWrap.appendChild(label);
      textWrap.appendChild(range);
      meta.appendChild(textWrap);
      meta.appendChild(value);
      meter.appendChild(fill);
      band.appendChild(meta);
      band.appendChild(meter);
      bandsEl.appendChild(band);

      return { band: band, label: label, range: range, value: value, fill: fill };
    }

    function ensureRows(count) {
      while (rows.length < count) rows.push(createRow());
      while (rows.length > count) {
        const row = rows.pop();
        bandsEl.removeChild(row.band);
      }
    }

    function update(bands) {
      if (!Array.isArray(bands)) return;
      ensureRows(bands.length);

      bands.forEach(function(band, index) {
        const row = rows[index];
        const value = clamp(band.value);
        row.label.textContent = band.label || '';
        row.range.textContent = band.range || '';
        row.range.style.display = band.range ? 'inline' : 'none';
        row.value.textContent = Math.round(value * 100) + '%';
        row.fill.style.width = (value * 100) + '%';
        row.fill.style.color = band.color;
        row.fill.style.background = band.color;
      });
    }

    return { update: update };
  };
})();
