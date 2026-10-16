(() => {
  const widget = document.querySelector("[data-chatbot]");
  if (!widget) return;

  const panel = widget.querySelector("[data-chatbot-panel]");
  const toggle = widget.querySelector("[data-chatbot-toggle]");
  const closeButton = widget.querySelector("[data-chatbot-close]");
  const messages = widget.querySelector("[data-chatbot-messages]");
  const form = widget.querySelector("[data-chatbot-form]");
  const input = form.querySelector('input[name="message"]');
  const csrfToken = form.querySelector('input[name="csrf_token"]');
  const sendButton = form.querySelector('button[type="submit"]');
  let isSending = false;

  function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, className) {
    const message = document.createElement("div");
    message.className = `chatbot-message ${className}`;
    message.textContent = text;
    messages.appendChild(message);
    scrollToLatest();
    return message;
  }

  function addBooks(books) {
    if (!Array.isArray(books) || books.length === 0) return;

    const list = document.createElement("div");
    list.className = "chatbot-book-list";

    for (const book of books) {
      const link = document.createElement("a");
      link.className = "chatbot-book";
      link.href = book.url;

      const title = document.createElement("strong");
      title.textContent = book.title;
      link.appendChild(title);

      const details = document.createElement("span");
      details.textContent = [book.author, book.category]
        .filter(Boolean)
        .join(" · ");
      link.appendChild(details);

      if (book.publisher || book.stock !== undefined) {
        const availability = document.createElement("span");
        availability.textContent = [
          book.publisher ? `NXB: ${book.publisher}` : "",
          book.stock > 0 ? `Còn ${book.stock} cuốn` : "Tạm hết hàng",
        ]
          .filter(Boolean)
          .join(" · ");
        link.appendChild(availability);
      }

      if (book.description) {
        const description = document.createElement("small");
        description.textContent = book.description;
        link.appendChild(description);
      }

      const price = document.createElement("small");
      price.textContent = book.price;
      link.appendChild(price);
      list.appendChild(link);
    }

    messages.appendChild(list);
    scrollToLatest();
  }

  function openPanel() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    input.focus();
  }

  function closePanel() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    toggle.focus();
  }

  toggle.addEventListener("click", openPanel);
  closeButton.addEventListener("click", closePanel);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });

  document.addEventListener("click", (event) => {
    if (!panel.hidden && !widget.contains(event.target)) closePanel();
  });

  for (const promptButton of widget.querySelectorAll("[data-chatbot-prompt]")) {
    promptButton.addEventListener("click", () => {
      input.value = promptButton.dataset.chatbotPrompt;
      form.requestSubmit();
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || isSending) return;

    isSending = true;
    input.disabled = true;
    sendButton.disabled = true;
    addMessage(text, "chatbot-message-user");
    input.value = "";
    widget.querySelector(".chatbot-suggestions")?.remove();
    const pending = addMessage(
      form.dataset.pendingMessage,
      "chatbot-message-assistant chatbot-message-pending",
    );

    try {
      const response = await fetch(form.dataset.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken.value,
        },
        body: JSON.stringify({ message: text }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || form.dataset.errorMessage);

      pending.remove();
      addMessage(result.reply, "chatbot-message-assistant");
      addBooks(result.books);
    } catch (_error) {
      pending.remove();
      addMessage(
        form.dataset.errorMessage,
        "chatbot-message-assistant",
      );
    } finally {
      isSending = false;
      input.disabled = false;
      sendButton.disabled = false;
      input.focus();
    }
  });
})();
