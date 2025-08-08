document.addEventListener("DOMContentLoaded", function () {
  console.log("Sales form JavaScript loaded (Strips + Units)");

  // --- Elements ---
  const medicineSearchInput = document.getElementById("medicine-search");
  const medicineResultsContainer = document.getElementById("medicine-results");
  const selectedItemsBody = document.getElementById("selected-items-body");
  const discountInput = document.getElementById("discount");
  const subTotalDisplay = document.getElementById("sub_total_display");
  const totalAmountDisplay = document.getElementById("total_amount_display");
  const saleForm = document.getElementById("sale-form");
  const hiddenItemFieldsContainer = document.getElementById("hidden-item-fields");
  const customerSearchInput = document.getElementById("customer-search");
  const customerResultsContainer = document.getElementById("customer-results");
  const selectedCustomerDisplay = document.getElementById("selected-customer-display");
  const hiddenCustomerIdInput = document.getElementById("selected_customer_id");
  const clearCustomerButton = document.getElementById("clear-customer");

  let selectedItems = {}; // { medicineId: { data, strips, units } }

  // Debounce utility
  function debounce(func, delay) {
      let timeoutId;
      return function(...args) {
          clearTimeout(timeoutId);
          timeoutId = setTimeout(() => {
              func.apply(this, args);
          }, delay);
      };
  }

  // =========================
  // Customer Search
  // =========================
  const debouncedCustomerSearch = debounce(async (query) => {
    if (query.length < 1) {
      customerResultsContainer.innerHTML = "";
      customerResultsContainer.style.display = "none";
      return;
    }
    try {
      const response = await fetch(`/api/search_customers?query=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const customers = await response.json();
      displayCustomerResults(customers);
    } catch (error) {
      console.error("Error fetching customers:", error);
      customerResultsContainer.innerHTML = `<div class="list-group-item text-danger">Error searching customers.</div>`;
      customerResultsContainer.style.display = "block";
    }
  }, 300);

  customerSearchInput.addEventListener("input", () => {
    const query = customerSearchInput.value.trim();
    if (query === "" && !hiddenCustomerIdInput.value) {
        resetCustomerSelection();
    }
    debouncedCustomerSearch(query);
  });

  function displayCustomerResults(customers) {
    customerResultsContainer.innerHTML = "";
  
    if (customers.length === 0) {
      customerResultsContainer.innerHTML = `
        <div class="list-group-item">
          No customers found. 
          <a href="${addCustomerUrl}" class="text-primary">Add New</a>
        </div>
      `;
    } else {
      customers.forEach((cust) => {
        const item = document.createElement("button");
        item.type = "button";
        item.classList.add("list-group-item", "list-group-item-action");
        item.innerHTML = `
          ${cust.name} 
          <small class="text-muted float-end">${cust.phone || ""}</small>
        `;
        item.addEventListener("click", () => {
          selectCustomer(cust);
        });
        customerResultsContainer.appendChild(item);
      });
    }
  
    customerResultsContainer.style.display = "block";
  }
  
  function selectCustomer(customerData) {
    selectedCustomerDisplay.innerHTML = `
        <span class="fw-bold">${customerData.name}</span>
        <small class="text-muted ms-1">(${customerData.phone || "No Phone"})</small>
     `;
    hiddenCustomerIdInput.value = customerData.id;
    clearCustomerButton.style.display = "inline-block";
    customerSearchInput.value = "";
    customerSearchInput.placeholder = customerData.name;
    customerResultsContainer.innerHTML = "";
    customerResultsContainer.style.display = "none";
    console.log(`Selected Customer ID: ${customerData.id}`);
  }

  function resetCustomerSelection() {
    selectedCustomerDisplay.innerHTML = `<span class="text-muted">Selected: Walk-in Customer</span>`;
    hiddenCustomerIdInput.value = "";
    clearCustomerButton.style.display = "none";
    customerSearchInput.value = "";
    customerSearchInput.placeholder = "Type Name/Phone or leave blank for Walk-in...";
    console.log("Customer selection cleared (Walk-in)");
  }

  if (clearCustomerButton) {
    clearCustomerButton.addEventListener("click", resetCustomerSelection);
  }

  document.addEventListener("click", (e) => {
    if (!customerSearchInput.contains(e.target) && !customerResultsContainer.contains(e.target)) {
      customerResultsContainer.style.display = "none";
    }
    if (!medicineSearchInput.contains(e.target) && !medicineResultsContainer.contains(e.target)) {
      medicineResultsContainer.style.display = "none";
    }
  });

  // =========================
  // Medicine Search
  // =========================
  const debouncedMedicineSearch = debounce(async (query) => {
    if (query.length < 1) {
      medicineResultsContainer.innerHTML = "";
      medicineResultsContainer.style.display = "none";
      return;
    }
    try {
      const response = await fetch(`/api/search_medicines?query=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const medicines = await response.json();
      displayMedicineResults(medicines);
    } catch (error) {
      console.error("Error fetching medicines:", error);
      medicineResultsContainer.innerHTML = `<div class="list-group-item text-danger">Error searching medicines.</div>`;
      medicineResultsContainer.style.display = "block";
    }
  }, 300);

  medicineSearchInput.addEventListener("input", () => {
    debouncedMedicineSearch(medicineSearchInput.value.trim());
  });

  function displayMedicineResults(medicines) {
    medicineResultsContainer.innerHTML = "";
    if (medicines.length === 0) {
      medicineResultsContainer.innerHTML = `<div class="list-group-item">No available medicines found.</div>`;
    } else {
      medicines.forEach((med) => {
        const item = document.createElement("button");
        item.type = "button";
        item.classList.add("list-group-item", "list-group-item-action");
        item.innerHTML = `
                ${med.name} <small class="text-muted">(Batch: ${med.batch_number})</small>
                <span class="badge bg-secondary float-end ms-2">
                    Stock: ${med.quantity} | ₹${parseFloat(med.price_per_strip).toFixed(2)}/strip
                </span>`;
        item.addEventListener("click", () => {
          addSelectedItem(med);
        });
        medicineResultsContainer.appendChild(item);
      });
    }
    medicineResultsContainer.style.display = "block";
  }

  function addSelectedItem(medicineData) {
    if (selectedItems[medicineData._id]) {
      alert(`${medicineData.name} (Batch: ${medicineData.batch_number}) is already added.`);
      return;
    }
    selectedItems[medicineData._id] = { data: medicineData, strips: 0, units: 0 };
    renderSelectedItemsTable();
    calculateTotal();
    medicineSearchInput.value = "";
    medicineResultsContainer.innerHTML = "";
    medicineResultsContainer.style.display = "none";
  }

  function renderSelectedItemsTable() {
    selectedItemsBody.innerHTML = "";
    if (Object.keys(selectedItems).length === 0) {
        const placeholderRow = document.createElement("tr");
        placeholderRow.id = "no-items-row";
        placeholderRow.innerHTML = '<td colspan="8" class="text-center">No items added yet.</td>';
        selectedItemsBody.appendChild(placeholderRow);
        return;
    }

    for (const medId in selectedItems) {
        const item = selectedItems[medId];
        const med = item.data;
        const stripsInStock = Math.floor(med.quantity / med.units_per_strip);
        const unitsInStock = med.quantity % med.units_per_strip;
        const itemTotal = (med.price_per_strip * item.strips) + (med.price_per_unit * item.units);

        const row = document.createElement("tr");
        row.dataset.medicineId = medId;
        row.innerHTML = `
            <td>${med.name}</td>
            <td>${med.batch_number}</td>
            <td class="text-end">₹${parseFloat(med.price_per_strip).toFixed(2)}/strip</br>
            ₹${parseFloat(med.price_per_unit).toFixed(2)}/unit</td>
            <td class="text-center">${stripsInStock} strips, ${unitsInStock} units</td>
            <td>
                <input type="number" class="form-control form-control-sm item-strips" value="${item.strips}" min="0" max="${stripsInStock}" data-medicine-id="${medId}" style="width: 70px;"> strips
                <input type="number" class="form-control form-control-sm item-units" value="${item.units}" min="0" max="${med.units_per_strip - 1}" data-medicine-id="${medId}" style="width: 70px;"> units
            </td>
            <td class="item-total text-end">₹${itemTotal.toFixed(2)}</td>
            <td class="text-center">
                <button type="button" class="btn btn-danger btn-sm remove-item" data-medicine-id="${medId}" title="Remove Item">X</button>
            </td>
        `;
        selectedItemsBody.appendChild(row);
    }
    addTableEventListeners();
  }

  function addTableEventListeners() {
      document.querySelectorAll(".item-strips, .item-units").forEach(input => {
          input.addEventListener('input', handleQuantityChange);
          input.addEventListener('change', handleQuantityChange);
      });
      document.querySelectorAll(".remove-item").forEach(button => {
          button.addEventListener('click', handleRemoveItemClick);
      });
  }

  function handleQuantityChange(event) {
      const input = event.target;
      const medId = input.dataset.medicineId;
      const med = selectedItems[medId].data;
      let strips = parseInt(document.querySelector(`.item-strips[data-medicine-id="${medId}"]`).value, 10) || 0;
      let units = parseInt(document.querySelector(`.item-units[data-medicine-id="${medId}"]`).value, 10) || 0;

      // Total units calculation
      const totalUnitsRequested = (strips * med.units_per_strip) + units;
      if (totalUnitsRequested > med.quantity) {
          alert(`Only ${med.quantity} units available in stock for ${med.name}.`);
          // Reduce to max possible
          strips = Math.floor(med.quantity / med.units_per_strip);
          units = med.quantity % med.units_per_strip;
          document.querySelector(`.item-strips[data-medicine-id="${medId}"]`).value = strips;
          document.querySelector(`.item-units[data-medicine-id="${medId}"]`).value = units;
      }

      // Save values
      selectedItems[medId].strips = strips;
      selectedItems[medId].units = units;

      // Update row total
      const row = input.closest("tr");
      const itemTotalCell = row.querySelector(".item-total");
      const totalPrice = (med.price_per_strip * strips) + (med.price_per_unit * units);
      itemTotalCell.textContent = `₹${totalPrice.toFixed(2)}`;

      calculateTotal();
  }

  function handleRemoveItemClick(event) {
      const medId = event.target.dataset.medicineId;
      delete selectedItems[medId];
      renderSelectedItemsTable();
      calculateTotal();
  }

  // =========================
  // Totals & Discount
  // =========================
  function calculateTotal() {
      let subtotal = 0;
      for (const medId in selectedItems) {
          const item = selectedItems[medId];
          subtotal += (item.data.price_per_strip * item.strips) + (item.data.price_per_unit * item.units);
      }
      subTotalDisplay.value = subtotal.toFixed(2);
      applyDiscount();
  }

  function applyDiscount() {
      const subtotal = parseFloat(subTotalDisplay.value) || 0;
      let discount = parseFloat(discountInput.value) || 0;
      if (discount < 0) discount = 0;
      if (discount > subtotal) discount = subtotal;
      discountInput.value = discount.toFixed(2);
      totalAmountDisplay.value = (subtotal - discount).toFixed(2);
  }

  discountInput.addEventListener("input", applyDiscount);
  discountInput.addEventListener("change", applyDiscount);

  // =========================
  // Form Submission
  // =========================
  saleForm.addEventListener("submit", function (event) {
      hiddenItemFieldsContainer.innerHTML = "";

      if (Object.keys(selectedItems).length === 0) {
          alert("Please add at least one item to the sale.");
          event.preventDefault();
          return;
      }

      for (const medId in selectedItems) {
          const item = selectedItems[medId];
          const totalUnits = (item.strips * item.data.units_per_strip) + item.units;
          if (totalUnits <= 0) {
              alert(`Please enter a valid quantity for ${item.data.name}.`);
              event.preventDefault();
              return;
          }

          // Hidden fields
          const idInput = document.createElement("input");
          idInput.type = "hidden";
          idInput.name = "medicine_ids[]";
          idInput.value = medId;
          hiddenItemFieldsContainer.appendChild(idInput);

          const stripsInput = document.createElement("input");
          stripsInput.type = "hidden";
          stripsInput.name = "strips[]";
          stripsInput.value = item.strips;
          hiddenItemFieldsContainer.appendChild(stripsInput);

          const unitsInput = document.createElement("input");
          unitsInput.type = "hidden";
          unitsInput.name = "units[]";
          unitsInput.value = item.units;
          hiddenItemFieldsContainer.appendChild(unitsInput);

          const priceInput = document.createElement("input");
          priceInput.type = "hidden";
          priceInput.name = "prices[]";
          priceInput.value = (item.data.price_per_strip * item.strips) + (item.data.price_per_unit * item.units);
          hiddenItemFieldsContainer.appendChild(priceInput);
      }

      calculateTotal();
  });

  // Initial
  resetCustomerSelection();
  renderSelectedItemsTable();
  calculateTotal();

});
