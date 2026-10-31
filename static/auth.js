const roleSelect = document.querySelector("#role");
const companyField = document.querySelector("#company-field");
const companyInput = document.querySelector("#company");

function syncCompanyField() {
  const isEmployer = roleSelect.value === "employer";
  companyField.hidden = !isEmployer;
  companyInput.required = isEmployer;
}

roleSelect.addEventListener("change", syncCompanyField);
syncCompanyField();
