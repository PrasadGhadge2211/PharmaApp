document.addEventListener("DOMContentLoaded", function () {
  console.log("Sales form JavaScript loaded");

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

  let selectedItems = {}; // { medicineId: { data, quantity } }

  // Debounce function utility
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
  // Customer Search & Selection
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
      // Use the Flask-rendered URL from a global JS variable
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

  if (clearCustomerButton) { // Add listener only if button exists
    clearCustomerButton.addEventListener("click", resetCustomerSelection);
  }

  // Hide dropdowns when clicking outside
  document.addEventListener("click", (e) => {
    if (customerSearchInput && !customerSearchInput.contains(e.target) && customerResultsContainer && !customerResultsContainer.contains(e.target)) {
      customerResultsContainer.style.display = "none";
    }
    if (medicineSearchInput && !medicineSearchInput.contains(e.target) && medicineResultsContainer && !medicineResultsContainer.contains(e.target)) {
      medicineResultsContainer.style.display = "none";
    }
  });

  // =========================
  // Medicine Search & Table
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
                    Stock: ${med.quantity} | ₹${parseFloat(med.price).toFixed(2)}
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
    if (selectedItems[medicineData.id]) {
      alert(`${medicineData.name} (Batch: ${medicineData.batch_number}) is already added. Please adjust the quantity.`);
      return;
    }
    selectedItems[medicineData.id] = { data: medicineData, quantity: 1 };
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
        placeholderRow.innerHTML = '<td colspan="7" class="text-center">No items added yet.</td>';
        selectedItemsBody.appendChild(placeholderRow);
        return;
    }

    for (const medId in selectedItems) {
        const item = selectedItems[medId];
        const med = item.data;
        const quantity = item.quantity;
        const itemTotal = (parseFloat(med.price) * quantity).toFixed(2);
        const row = document.createElement("tr");
        row.dataset.medicineId = medId;

        row.innerHTML = `
            <td>${med.name}</td>
            <td>${med.batch_number}</td>
            <td class="text-end">${parseFloat(med.price).toFixed(2)}</td>
            <td class="text-center">${med.quantity}</td>
            <td>
                <input type="number" class="form-control form-control-sm item-quantity" value="${quantity}" min="1" max="${med.quantity}" data-medicine-id="${medId}" required style="width: 80px;">
            </td>
            <td class="item-total text-end">₹${itemTotal}</td>
            <td class="text-center">
                <button type="button" class="btn btn-danger btn-sm remove-item" data-medicine-id="${medId}" title="Remove Item">X</button>
            </td>
        `;
        selectedItemsBody.appendChild(row);
    }
    addTableEventListeners();
  }

  function addTableEventListeners() {
      document.querySelectorAll(".item-quantity").forEach(input => {
          input.removeEventListener('input', handleQuantityChange);
          input.addEventListener('input', handleQuantityChange);
          input.removeEventListener('change', handleQuantityChange);
          input.addEventListener('change', handleQuantityChange); // Use change for final validation if needed
      });
      document.querySelectorAll(".remove-item").forEach(button => {
          button.removeEventListener('click', handleRemoveItemClick);
          button.addEventListener('click', handleRemoveItemClick);
      });
  }

  function handleQuantityChange(event) {
      const input = event.target;
      const medId = input.dataset.medicineId;
      let newQuantity = parseInt(input.value, 10);
      const maxQuantity = parseInt(input.max, 10);

      if (isNaN(newQuantity) || newQuantity < 1) {
          newQuantity = 1;
          input.value = 1; // Correct invalid input
      } else if (newQuantity > maxQuantity) {
          newQuantity = maxQuantity;
          input.value = maxQuantity; // Cap at max stock
          alert(`Only ${maxQuantity} items available for ${selectedItems[medId].data.name} (Batch: ${selectedItems[medId].data.batch_number}).`);
      }

      if (selectedItems[medId]) {
          selectedItems[medId].quantity = newQuantity;
          const row = input.closest("tr");
          const itemTotalCell = row.querySelector(".item-total");
          const price = selectedItems[medId].data.price;
          itemTotalCell.textContent = `₹${(price * newQuantity).toFixed(2)}`;
          calculateTotal(); // Recalculate overall totals
      }
  }

  function handleRemoveItemClick(event) {
      const button = event.target;
      const medId = button.dataset.medicineId;
      if (selectedItems[medId]) {
          delete selectedItems[medId];
          renderSelectedItemsTable(); // Re-render the table
          calculateTotal(); // Recalculate totals
      }
  }

  // =========================
  // Totals Calculation & Form Submission
  // =========================

  function calculateTotal() {
      let subtotal = 0;
      for (const medId in selectedItems) {
          const item = selectedItems[medId];
          subtotal += item.data.price * item.quantity;
      }
      subTotalDisplay.value = subtotal.toFixed(2); // Update subtotal input
      applyDiscount(); // Recalculate grand total after subtotal changes
  }

  function applyDiscount() {
      const subtotal = parseFloat(subTotalDisplay.value) || 0;
      let discount = parseFloat(discountInput.value) || 0;

      if (discount < 0) {
          discount = 0;
          discountInput.value = discount.toFixed(2);
      } else if (discount > subtotal) {
          discount = subtotal;
          discountInput.value = discount.toFixed(2);
          // Optionally alert user discount was capped
          // alert("Discount cannot exceed subtotal.");
      }

      const grandTotal = subtotal - discount;
      totalAmountDisplay.value = grandTotal.toFixed(2); // Update total input
  }

  // Add event listeners for discount changes
  discountInput.addEventListener("input", applyDiscount);
  discountInput.addEventListener("change", applyDiscount); // Handles pasting/direct set

  // Form Submission Logic
  saleForm.addEventListener("submit", function (event) {
      hiddenItemFieldsContainer.innerHTML = ""; // Clear previous hidden fields

      if (Object.keys(selectedItems).length === 0) {
          alert("Please add at least one item to the sale.");
          event.preventDefault(); // Prevent form submission
          return;
      }

      let isValid = true;
      // Add hidden fields for each item
      for (const medId in selectedItems) {
          const item = selectedItems[medId];

          if (item.quantity <= 0) { // Final check before submission
              alert(`Quantity for ${item.data.name} must be positive.`);
              isValid = false;
              break;
          }

          // Medicine ID (links to the specific batch)
          const idInput = document.createElement("input");
          idInput.type = "hidden";
          idInput.name = "medicine_ids[]";
          idInput.value = medId;
          hiddenItemFieldsContainer.appendChild(idInput);

          // Quantity
          const qtyInput = document.createElement("input");
          qtyInput.type = "hidden";
          qtyInput.name = "quantities[]";
          qtyInput.value = item.quantity;
          hiddenItemFieldsContainer.appendChild(qtyInput);

          // Price (at time of sale)
          const priceInput = document.createElement("input");
          priceInput.type = "hidden";
          priceInput.name = "prices[]";
          priceInput.value = item.data.price;
          hiddenItemFieldsContainer.appendChild(priceInput);
      }

      if (!isValid) {
          event.preventDefault(); // Prevent form submission if validation failed
          return;
      }

      // Recalculate final total one last time before submission (optional, belt-and-suspenders)
      calculateTotal();

      // Allow form submission to proceed
      console.log("Submitting sale...");
  });

  // --- Initial Setup ---
  resetCustomerSelection(); // Ensure walk-in is default
  renderSelectedItemsTable(); // Render empty table initially
  calculateTotal(); // Calculate initial totals (should be 0)

}); // End DOMContentLoaded