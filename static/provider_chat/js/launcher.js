(function () {
  "use strict";

  var launcher = document.querySelector(".provider-chat-launcher");
  var invite = document.querySelector("[data-chat-invite]");
  var inviteText = document.querySelector("[data-chat-invite-text]");

  if (!launcher || !invite || !inviteText) return;

  var message =
    invite.dataset.message || "Ask me LGBTQ+ health questions or find a provider.";
  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;
  var typeTimer;
  var dismissTimer;
  var repeatTimer;

  function hideInvite() {
    window.clearTimeout(dismissTimer);
    invite.classList.remove("is-visible");
  }

  function scheduleRepeat(delay) {
    window.clearTimeout(dismissTimer);
    window.clearTimeout(repeatTimer);
    dismissTimer = window.setTimeout(function () {
      hideInvite();
      repeatTimer = window.setTimeout(beginInvitation, 300);
    }, delay);
  }

  function finishTyping() {
    invite.classList.remove("is-typing");
    inviteText.textContent = message;
    scheduleRepeat(3000);
  }

  function typeMessage(index) {
    if (index > message.length) {
      finishTyping();
      return;
    }

    inviteText.textContent = message.slice(0, index);
    typeTimer = window.setTimeout(function () {
      typeMessage(index + 1);
    }, 34);
  }

  function beginInvitation() {
    window.clearTimeout(typeTimer);
    window.clearTimeout(dismissTimer);
    window.clearTimeout(repeatTimer);
    inviteText.textContent = "";
    invite.classList.remove("is-visible", "is-typing");
    invite.hidden = false;
    launcher.classList.add("is-inviting");

    window.setTimeout(function () {
      invite.classList.add("is-visible", "is-typing");
    }, prefersReducedMotion ? 0 : 500);

    window.setTimeout(function () {
      launcher.classList.remove("is-inviting");
      if (prefersReducedMotion) {
        finishTyping();
      } else {
        invite.classList.remove("is-typing");
        typeMessage(1);
      }
    }, prefersReducedMotion ? 50 : 1650);
  }

  invite.addEventListener("mouseenter", function () {
    window.clearTimeout(dismissTimer);
    window.clearTimeout(repeatTimer);
  });

  invite.addEventListener("mouseleave", function () {
    if (!invite.classList.contains("is-typing")) {
      scheduleRepeat(3000);
    }
  });

  window.addEventListener("pagehide", function () {
    window.clearTimeout(typeTimer);
    window.clearTimeout(dismissTimer);
    window.clearTimeout(repeatTimer);
  });

  window.setTimeout(beginInvitation, prefersReducedMotion ? 300 : 900);
})();
