// Sales form functionality
document.addEventListener("DOMContentLoaded", function () {
  // Add new item row
  document.getElementById("add-item")?.addEventListener("click", function () {
    const container = document.getElementById("items-container");
    const newRow = container.querySelector(".item-row").cloneNode(true);

    // Clear selected medicine and reset values
    newRow.querySelector(".medicine-select").selectedIndex = 0;
    newRow.querySelector(".quantity").value = 1;
    newRow.querySelector(".price").value = "";

    container.appendChild(newRow);
  });

  // Remove item row
  document.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-item")) {
      const row = e.target.closest(".item-row");
      if (document.querySelectorAll(".item-row").length > 1) {
        row.remove();
      } else {
        // Reset the single row instead of removing it
        const select = row.querySelector(".medicine-select");
        select.selectedIndex = 0;
        row.querySelector(".quantity").value = 1;
        row.querySelector(".price").value = "";
      }
    }
  });

  // Update price when medicine is selected
  document.addEventListener("change", function (e) {
    if (e.target.classList.contains("medicine-select") && e.target.value) {
      const selectedOption = e.target.options[e.target.selectedIndex];
      const price = selectedOption.dataset.price;
      const row = e.target.closest(".item-row");
      row.querySelector(".price").value = price;
    }
  });
});

// Helper function for printing
function printInvoice() {
  window.print();
}
