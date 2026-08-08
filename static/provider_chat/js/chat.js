(function () {
  "use strict";

  var app = document.getElementById("provider-chat-app");
  if (!app) return;

  var storageKey = "affirmcare.providerChat.v1";
  var welcomeMessage =
    "Welcome to Affirm Care. Whether you have a question or need help finding care, I'm here to help.";
  var messageList = document.getElementById("chat-message-list");
  var suggestions = document.getElementById("chat-suggestions");
  var suggestionTrack = document.getElementById("chat-suggestion-track");
  var resultsSection = document.getElementById("chat-results");
  var resultsTrack = document.getElementById("chat-results-track");
  var seeAllLink = document.getElementById("chat-see-all-link");
  var composer = document.getElementById("chat-composer");
  var composerDock = document.getElementById("chat-composer-dock");
  var footer = document.getElementById("footer");
  var input = document.getElementById("chat-message-input");
  var sendButton = document.getElementById("chat-send-button");
  var resetButton = document.getElementById("chat-reset-button");
  var previousButton = document.getElementById("chat-results-previous");
  var nextButton = document.getElementById("chat-results-next");
  var csrfInput = composer.querySelector("input[name='csrfmiddlewaretoken']");
  var ttlMs = Number(app.dataset.conversationTtlMs) || 86400000;
  var isLoading = false;
  var transientError = "";
  var state = loadState();
  var hasSuggestions = Boolean(suggestionTrack && suggestionTrack.children.length);
  var nearbyRequestPattern = /\b(?:near\s+(?:me|my (?:location|area)|where i am)|nearby(?:\s+(?:me|here))?|closest(?:\s+(?:to|near)\s+me)?|close\s+to\s+me|around\s+here|in\s+my\s+area|at\s+my\s+location|my\s+location|where\s+i\s+am|local\s+providers?)\b/i;

  if (window.ResizeObserver) {
    var layoutResizeObserver = new ResizeObserver(updateFixedLayoutClearance);
    layoutResizeObserver.observe(app);
    layoutResizeObserver.observe(composerDock);
    if (footer) layoutResizeObserver.observe(footer);
  } else {
    window.addEventListener("resize", updateFixedLayoutClearance);
  }
  updateFixedLayoutClearance();

  render();
  focusInput();

  composer.addEventListener("submit", function (event) {
    event.preventDefault();
    sendMessage(input.value);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  input.addEventListener("input", resizeInput);

  suggestions.addEventListener("click", function (event) {
    var button = event.target.closest("[data-prompt]");
    if (!button || isLoading) return;
    input.value = button.dataset.prompt;
    resizeInput();
    sendMessage(input.value);
  });

  resetButton.addEventListener("click", function () {
    if (
      state.messages.length &&
      !window.confirm("Start a new conversation and clear this chat history?")
    ) {
      return;
    }
    state = emptyState();
    transientError = "";
    persistState();
    render();
    focusInput();
  });

  previousButton.addEventListener("click", function () {
    scrollResults(-1);
  });

  nextButton.addEventListener("click", function () {
    scrollResults(1);
  });

  resultsTrack.addEventListener("scroll", updateCarouselControls, { passive: true });

  resultsTrack.addEventListener("keydown", function (event) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    scrollResults(event.key === "ArrowLeft" ? -1 : 1);
  });

  async function sendMessage(rawMessage) {
    var message = rawMessage.trim();
    if (!message || isLoading) return;

    transientError = "";
    isLoading = true;
    state.messages.push({ role: "user", text: message });
    state.messages = state.messages.slice(-40);
    state.updatedAt = Date.now();
    input.value = "";
    resizeInput();
    persistState();
    render();

    var location;
    if (isNearbyRequest(message)) {
      try {
        location = await requestCurrentLocation();
      } catch (error) {
        isLoading = false;
        state.messages.push({
          role: "assistant",
          text: locationErrorMessage(error)
        });
        state.messages = state.messages.slice(-40);
        state.updatedAt = Date.now();
        persistState();
        render();
        focusInput();
        return;
      }
    }

    var payload = { message: message };
    if (location) {
      payload.latitude = location.latitude;
      payload.longitude = location.longitude;
    }
    if (state.conversationId) payload.conversation_id = state.conversationId;
    if (app.dataset.providerSlug) payload.provider_slug = app.dataset.providerSlug;

    try {
      var response = await fetch(app.dataset.apiUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfInput.value
        },
        body: JSON.stringify(payload)
      });
      var data = await response.json().catch(function () {
        return {};
      });

      if (!response.ok) {
        var code = data.error && data.error.code;
        if (code === "conversation_not_found") {
          state.conversationId = null;
          state.latestResults = [];
          state.latestFilters = {};
          state.latestCount = 0;
          persistState();
          throw new Error(
            "This conversation expired. Your visible history is still here, but your next message will begin a new provider search."
          );
        }
        throw new Error(
          (data.error && data.error.message) ||
            "The provider assistant could not complete that request."
        );
      }

      state.conversationId = data.conversation_id || state.conversationId;
      state.messages.push({
        role: "assistant",
        text: data.assistant_message || "I completed your request.",
        intent: data.intent || ""
      });
      if (data.intent === "search_providers" || data.intent === "provider_details") {
        state.latestResults = Array.isArray(data.results) ? data.results : [];
        state.latestFilters =
          data.intent === "search_providers" && data.filters
            ? data.filters
            : {};
        state.latestSort = data.sort || "name";
        state.latestCount = Number(data.count) || state.latestResults.length;
      }
      state.messages = state.messages.slice(-40);
      state.updatedAt = Date.now();
      persistState();
    } catch (error) {
      transientError = error.message || "The provider assistant is unavailable right now.";
    } finally {
      isLoading = false;
      render();
      if (state.latestResults.length && !transientError) {
        window.requestAnimationFrame(function () {
          resultsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
      }
      focusInput();
    }
  }

  function render() {
    renderMessages();
    renderResults();
    suggestions.hidden = !hasSuggestions || state.messages.some(function (message) {
      return message.role === "user";
    });
    sendButton.disabled = isLoading;
    input.disabled = isLoading;
    window.requestAnimationFrame(function () {
      scrollConversationToLatest();
    });
  }

  function scrollConversationToLatest() {
    if (!state.messages.length && !isLoading && !transientError) return;
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: "smooth"
    });
  }

  function isNearbyRequest(message) {
    return nearbyRequestPattern.test(message);
  }

  function requestCurrentLocation() {
    if (!navigator.geolocation) {
      return Promise.reject(new Error("unsupported"));
    }
    return new Promise(function (resolve, reject) {
      navigator.geolocation.getCurrentPosition(
        function (position) {
          resolve({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude
          });
        },
        reject,
        { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 }
      );
    });
  }

  function locationErrorMessage(error) {
    if (error && error.code === 1) {
      return "Location access was not granted. Share a city, state, or ZIP code and I’ll find providers there.";
    }
    if (error && error.message === "unsupported") {
      return "This browser cannot share your location. Share a city, state, or ZIP code and I’ll find providers there.";
    }
    return "I couldn’t determine your location. Check that location services are available, or share a city, state, or ZIP code.";
  }

  function updateFixedLayoutClearance() {
    var composerHeight = composerDock.offsetHeight + "px";
    var footerHeight = footer ? footer.offsetHeight + "px" : "0px";
    var shellBounds = app.getBoundingClientRect();
    var shellWidth = shellBounds.width + "px";
    var shellCenter = shellBounds.left + shellBounds.width / 2 + "px";
    app.style.setProperty(
      "--chat-composer-dock-height",
      composerHeight
    );
    document.body.style.setProperty(
      "--chat-composer-dock-height",
      composerHeight
    );
    app.style.setProperty("--chat-footer-height", footerHeight);
    document.body.style.setProperty("--chat-footer-height", footerHeight);
    app.style.setProperty("--chat-shell-rendered-width", shellWidth);
    document.body.style.setProperty("--chat-shell-rendered-width", shellWidth);
    app.style.setProperty("--chat-shell-rendered-center", shellCenter);
    document.body.style.setProperty("--chat-shell-rendered-center", shellCenter);
  }

  function renderMessages() {
    messageList.replaceChildren();
    appendMessage("assistant", welcomeMessage);
    state.messages.forEach(function (message) {
      appendMessage(message.role, message.text);
    });
    if (isLoading) appendTypingIndicator();
    if (transientError) appendMessage("assistant", transientError, true);
  }

  function appendMessage(role, text, isError) {
    var row = document.createElement("div");
    row.className = "chat-message-row " + (role === "user" ? "is-user" : "is-assistant");
    if (isError) row.classList.add("is-error");

    if (role !== "user") {
      var avatar = document.createElement("span");
      avatar.className = "chat-assistant-avatar";
      avatar.setAttribute("aria-hidden", "true");
      var icon = createBotIcon();
      avatar.appendChild(icon);
      row.appendChild(avatar);
    }

    var bubble = document.createElement("div");
    bubble.className = "chat-message-bubble";
    bubble.textContent = text;
    row.appendChild(bubble);
    messageList.appendChild(row);
  }

  function appendTypingIndicator() {
    var row = document.createElement("div");
    row.className = "chat-message-row is-assistant";
    row.setAttribute("aria-label", "Assistant is searching");

    var avatar = document.createElement("span");
    avatar.className = "chat-assistant-avatar";
    avatar.setAttribute("aria-hidden", "true");
    var icon = createBotIcon();
    avatar.appendChild(icon);

    var bubble = document.createElement("div");
    bubble.className = "chat-message-bubble";
    var dots = document.createElement("span");
    dots.className = "chat-typing-dots";
    dots.setAttribute("aria-hidden", "true");
    dots.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    bubble.appendChild(dots);
    row.append(avatar, bubble);
    messageList.appendChild(row);
  }

  function createBotIcon() {
    var icon = document.createElement("img");
    icon.className = "chat-assistant-avatar-icon";
    icon.src = app.dataset.botIconUrl;
    icon.alt = "";
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function renderResults() {
    resultsTrack.replaceChildren();
    if (!state.latestResults.length) {
      resultsSection.hidden = true;
      seeAllLink.hidden = true;
      return;
    }

    state.latestResults.forEach(function (provider) {
      resultsTrack.appendChild(createProviderCard(provider));
    });
    resultsTrack.scrollLeft = 0;
    updateSeeAllLink();
    resultsSection.hidden = false;
    window.requestAnimationFrame(updateCarouselControls);
  }

  function updateSeeAllLink() {
    var filters = state.latestFilters || {};
    if (!Object.keys(filters).length) {
      seeAllLink.hidden = true;
      return;
    }

    var params = new URLSearchParams();
    appendSearchValue(params, "keyword", filters.keyword);
    appendSearchValue(params, "city", filters.city);
    appendSearchValue(params, "state", filters.state_code);
    appendSearchValue(params, "zip_code", filters.zip_code);
    appendSearchValues(params, "service", filters.service_slugs);
    appendSearchValues(params, "features", filters.affirming_feature_codes);
    appendSearchValues(params, "org_type", filters.org_types);
    appendSearchValues(params, "delivery_mode", filters.delivery_modes);
    appendSearchValues(params, "age_group", filters.age_groups);
    appendSearchValue(params, "verified_after", filters.verified_after);

    [
      "wheelchair_accessible",
      "gender_neutral_restrooms",
      "public_transit_access",
      "has_booking_url",
      "has_website_url"
    ].forEach(function (name) {
      if (typeof filters[name] === "boolean") {
        params.append(name, filters[name] ? "true" : "false");
      }
    });

    if (state.latestSort && state.latestSort !== "name") {
      params.append("sort", state.latestSort);
    }

    var query = params.toString();
    seeAllLink.href = app.dataset.providerResultsUrl + (query ? "?" + query : "");
    seeAllLink.setAttribute(
      "aria-label",
      "See all " + state.latestCount + " provider matches"
    );
    seeAllLink.hidden = false;
  }

  function appendSearchValue(params, name, value) {
    if (value === null || value === undefined || value === "") return;
    params.append(name, String(value));
  }

  function appendSearchValues(params, name, values) {
    if (!Array.isArray(values)) return;
    values.forEach(function (value) {
      appendSearchValue(params, name, value);
    });
  }

  function createProviderCard(provider) {
    var link = document.createElement("a");
    link.className = "chat-provider-card";
    link.href = app.dataset.providerDetailTemplate.replace(
      "__provider_slug__",
      encodeURIComponent(provider.slug)
    );
    link.setAttribute("aria-label", "View " + provider.name + " provider details");

    var type = document.createElement("span");
    type.className = "chat-provider-type";
    type.textContent = formatChoice(provider.org_type || "Provider");

    var title = document.createElement("h3");
    title.textContent = provider.name || "Provider";

    var services = document.createElement("p");
    services.className = "chat-provider-services";
    services.textContent = serviceNames(provider).join(", ") || "Services not listed";

    var location = document.createElement("p");
    location.className = "chat-provider-meta";
    var locationIcon = document.createElement("i");
    locationIcon.className = "fa-solid fa-location-dot";
    locationIcon.setAttribute("aria-hidden", "true");
    var locationText = document.createElement("span");
    locationText.textContent = providerLocation(provider);
    location.append(locationIcon, locationText);

    var action = document.createElement("span");
    action.className = "chat-provider-action";
    var actionText = document.createElement("span");
    actionText.textContent = "View provider details";
    var actionIcon = document.createElement("i");
    actionIcon.className = "fa-solid fa-arrow-right";
    actionIcon.setAttribute("aria-hidden", "true");
    action.append(actionText, actionIcon);

    link.append(type, title, services, location, action);
    return link;
  }

  function serviceNames(provider) {
    if (!Array.isArray(provider.services)) return [];
    return provider.services
      .map(function (entry) {
        return entry && entry.service && entry.service.name;
      })
      .filter(Boolean);
  }

  function providerLocation(provider) {
    var location = provider.primary_location;
    if (!location && Array.isArray(provider.locations)) location = provider.locations[0];
    if (!location) return "Location not listed";
    var place = [location.city, location.state_code].filter(Boolean).join(", ") || "Location not listed";
    if (typeof provider.distance_miles === "number") {
      return provider.distance_miles.toFixed(1) + " mi away · " + place;
    }
    return place;
  }

  function formatChoice(value) {
    return String(value)
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (letter) {
        return letter.toUpperCase();
      });
  }

  function scrollResults(direction) {
    var firstCard = resultsTrack.querySelector(".chat-provider-card");
    var cardGap = parseFloat(window.getComputedStyle(resultsTrack).columnGap) || 0;
    var scrollDistance = firstCard
      ? firstCard.getBoundingClientRect().width + cardGap
      : Math.max(280, resultsTrack.clientWidth * 0.8);

    resultsTrack.scrollBy({
      left: direction * scrollDistance,
      behavior: "smooth"
    });
  }

  function updateCarouselControls() {
    var maximumScroll = Math.max(0, resultsTrack.scrollWidth - resultsTrack.clientWidth);
    previousButton.disabled = resultsTrack.scrollLeft <= 1;
    nextButton.disabled = resultsTrack.scrollLeft >= maximumScroll - 1;
  }

  function resizeInput() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 132) + "px";
  }

  function focusInput() {
    input.focus({ preventScroll: true });
  }

  function emptyState() {
    return {
      conversationId: null,
      messages: [],
      latestResults: [],
      latestFilters: {},
      latestSort: "name",
      latestCount: 0,
      updatedAt: Date.now()
    };
  }

  function loadState() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(storageKey));
      if (!parsed || Date.now() - Number(parsed.updatedAt || 0) > ttlMs) {
        window.localStorage.removeItem(storageKey);
        return emptyState();
      }
      return {
        conversationId:
          typeof parsed.conversationId === "string" ? parsed.conversationId : null,
        messages: Array.isArray(parsed.messages) ? parsed.messages.slice(-40) : [],
        latestResults: Array.isArray(parsed.latestResults) ? parsed.latestResults : [],
        latestFilters:
          parsed.latestFilters && typeof parsed.latestFilters === "object"
            ? parsed.latestFilters
            : {},
        latestSort:
          typeof parsed.latestSort === "string" ? parsed.latestSort : "name",
        latestCount: Number(parsed.latestCount) || 0,
        updatedAt: Number(parsed.updatedAt) || Date.now()
      };
    } catch (error) {
      return emptyState();
    }
  }

  function persistState() {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state));
    } catch (error) {
      // The chat still works when browser storage is disabled.
    }
  }
})();
