document.addEventListener("DOMContentLoaded", function () {
  const toggleBtn = document.getElementById("sidebarToggle");
  const sidebar = document.querySelector(".sidebar");
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", function () {
      sidebar.classList.toggle("show");
    });
  }

  // Auto-dismiss alerts after 4s
  document.querySelectorAll(".alert-dismissible").forEach(function (alertEl) {
    setTimeout(function () {
      const alert = bootstrap.Alert.getOrCreateInstance(alertEl);
      alert.close();
    }, 4000);
  });
});

function chartColors() {
  return ["#2f6bff", "#f97066", "#12b76a", "#f79009", "#9b8afb", "#06aed4", "#ee46bc", "#667085"];
}
