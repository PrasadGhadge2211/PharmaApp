document.addEventListener("DOMContentLoaded", function () {
  const addBySelect = document.getElementById('add_by');
  const stripFields = document.getElementById('strip-fields');
  const unitFields = document.getElementById('unit-fields');

  // strip inputs
  const stripsCountInput = document.getElementById('strips_count');
  const unitsPerStripInput = document.getElementById('units_per_strip');
  const pricePerStripInput = document.getElementById('price_per_strip');
  const pricePerUnitInput = document.getElementById('price_per_unit');

  // unit inputs
  const quantityInput = document.getElementById('quantity');
  const pricePerUnitSingleInput = document.getElementById('price_per_unit_single');

  function toggleFields() {
    const mode = addBySelect.value;
    if (mode === 'strip') {
      stripFields.style.display = '';
      unitFields.style.display = 'none';
      // copy single price into strip per-unit if empty
      if (pricePerUnitInput && pricePerUnitSingleInput && pricePerUnitInput.value == '0.00' && pricePerUnitSingleInput.value) {
        pricePerUnitInput.value = pricePerUnitSingleInput.value;
      }
    } else {
      stripFields.style.display = 'none';
      unitFields.style.display = '';
    }
  }

  function calculatePerUnitFromStrip() {
    const unitsPerStrip = parseInt(unitsPerStripInput.value, 10) || 0;
    const pricePerStrip = parseFloat(pricePerStripInput.value) || 0;
    if (unitsPerStrip > 0) {
      const value = pricePerStrip / unitsPerStrip;
      // Round to 2 decimals and don't override when user manually edits (but we want live update)
      pricePerUnitInput.value = value.toFixed(2);
    } else {
      pricePerUnitInput.value = "0.00";
    }
  }

  // Recalculate when units per strip or price per strip changes
  unitsPerStripInput.addEventListener('input', calculatePerUnitFromStrip);
  pricePerStripInput.addEventListener('input', calculatePerUnitFromStrip);

  // If user edits the price_per_unit manually, we respect it. But if price_per_strip or units change, we update again.
  pricePerUnitInput.addEventListener('input', function () {
    // Allow manual edit; no special action required
  });

  // When switching to "unit" mode, copy the price per unit into the single unit field for convenience
  addBySelect.addEventListener('change', function () {
    if (addBySelect.value === 'unit') {
      if (pricePerUnitInput && pricePerUnitInput.value && (!pricePerUnitSingleInput.value || pricePerUnitSingleInput.value === '0.00')) {
        pricePerUnitSingleInput.value = pricePerUnitInput.value;
      }
      if (quantityInput && quantityInput.value === '0') {
        quantityInput.value = 1;
      }
    }
    toggleFields();
  });

  // initial setup
  toggleFields();
  calculatePerUnitFromStrip();
});
