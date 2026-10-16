(() => {
  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = document.getElementById(button.dataset.passwordToggle);
    const icon = button.querySelector("i");
    if (!input || !icon) return;

    button.addEventListener("click", () => {
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      icon.classList.toggle("bi-eye", !isHidden);
      icon.classList.toggle("bi-eye-slash", isHidden);
      button.setAttribute(
        "aria-label",
        isHidden ? button.dataset.hideLabel : button.dataset.showLabel,
      );
    });
  });
})();
