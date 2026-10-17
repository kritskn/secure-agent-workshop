// Display the recorded instant locally; never replace it with the current time.
// No timezone/geolocation request, storage, or data sent back to the server.
for (const time of document.querySelectorAll("time[data-local-time]")) {
  try {
    const instant = new Date(time.dateTime);
    const date = time.querySelector(".date");
    const clock = time.querySelector(".clock");
    const zone = time.querySelector(".zone");
    if (!date || !clock || !zone) continue;

    const localDate = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
    }).format(instant);
    const localClock = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      fractionalSecondDigits: 3, hourCycle: "h23",
    }).format(instant);
    const localZone = new Intl.DateTimeFormat(undefined, {
      timeZoneName: "short",
    }).formatToParts(instant).find((part) => part.type === "timeZoneName").value;

    date.textContent = localDate;
    clock.textContent = localClock;
    zone.textContent = localZone;
  } catch {
    // Invalid timestamps or unavailable Intl support retain the complete UTC fallback.
  }
}
