// This file intentionally contains no API key. It only talks to your server.
const API_URL = window.BIRDVIRUS_API_URL || "/api/chat";
const form = document.querySelector("#chat-form");
const input = document.querySelector("#prompt");
const sendButton = document.querySelector("#send");
const messages = document.querySelector("#messages");

function addMessage(role, text) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  const label = document.createElement("p");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Birdvirus Cloud";
  const content = document.createElement("p");
  content.textContent = text;
  message.append(label, content);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  addMessage("user", prompt);
  input.value = "";
  sendButton.disabled = true;
  const pending = addMessage("assistant", "Thinking…");
  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The cloud is unavailable right now.");
    pending.querySelector("p:last-child").textContent = data.answer;
  } catch (error) {
    pending.querySelector("p:last-child").textContent = error.message;
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});
