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
      .spectral-debug.is-visible {
        display: block;
        pointer-events: auto;
      }
      .spectral-debug__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 10px;
      }
      .spectral-debug__title {
        color: rgba(255, 255, 255, 0.9);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
      }
      .spectral-debug__close,
      .spectral-debug__toggle {
        border: 1px solid rgba(255, 255, 255, 0.16);
        background: rgba(0, 0, 0, 0.82);
        color: rgba(255, 255, 255, 0.88);
        font-family: inherit;
        cursor: pointer;
      }
      .spectral-debug__close {
        width: 24px;
        height: 24px;
        border-radius: 999px;
        font-size: 16px;
        line-height: 1;
      }
      .spectral-debug__toggle {
        position: fixed;
        right: 16px;
        bottom: 16px;
        width: 44px;
        height: 44px;
        display: none;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        font-size: 20px;
        z-index: 21;
        pointer-events: auto;
        box-shadow: 0 0 18px rgba(255, 255, 255, 0.1);
      }
      .spectral-debug__toggle.is-visible {
        display: flex;
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
    const header = document.createElement('div');
    const title = document.createElement('div');
    const closeButton = document.createElement('button');
    const toggleButton = document.createElement('button');
    const bandsEl = document.createElement('div');
    const footer = document.createElement('div');
    const rows = [];
    const touchToggleQuery = window.matchMedia('(pointer: coarse), (max-width: 768px)');
    let showTouchToggle = touchToggleQuery.matches;

    root.className = 'spectral-debug';
    header.className = 'spectral-debug__header';
    title.className = 'spectral-debug__title';
    title.textContent = config.title || 'spectral analyser';
    closeButton.className = 'spectral-debug__close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', 'Close spectral analyser');
    closeButton.textContent = '×';
    toggleButton.className = 'spectral-debug__toggle';
    toggleButton.type = 'button';
    toggleButton.setAttribute('aria-label', 'Toggle spectral analyser');
    toggleButton.textContent = '≋';
    bandsEl.className = 'spectral-debug__bands';
    footer.className = 'spectral-debug__footer';
    function updateFooterText() {
      footer.textContent = config.footer || (showTouchToggle ? 'tap the analyser icon to open · tap close to dismiss' : 'press S to toggle');
    }

    updateFooterText();
    header.appendChild(title);
    header.appendChild(closeButton);
    root.appendChild(header);
    root.appendChild(bandsEl);
    root.appendChild(footer);
    document.body.appendChild(root);
    document.body.appendChild(toggleButton);
    let visible = false;

    function syncVisibility() {
      root.classList.toggle('is-visible', visible);
      toggleButton.classList.toggle('is-visible', showTouchToggle && !visible);
    }

    function setVisible(nextVisible) {
      visible = !!nextVisible;
      syncVisibility();
    }

    function toggleVisible() {
      setVisible(!visible);
    }

    function handleTouchToggleQueryChange(event) {
      showTouchToggle = event.matches;
      updateFooterText();
      syncVisibility();
    }

    document.addEventListener('keydown', function(event) {
      if (event.repeat) return;
      if ((event.key || '').toLowerCase() !== 's') return;
      toggleVisible();
    });
    if (touchToggleQuery.addEventListener) {
      touchToggleQuery.addEventListener('change', handleTouchToggleQueryChange);
    } else if (touchToggleQuery.addListener) {
      touchToggleQuery.addListener(handleTouchToggleQueryChange);
    }
    toggleButton.addEventListener('click', toggleVisible);
    closeButton.addEventListener('click', function() { setVisible(false); });
    syncVisibility();

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
