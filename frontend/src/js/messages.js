// Turns an /interpret result into what the screen shows and what is spoken aloud.
// Safety: English is shown and spoken ONLY for status "match". Everything else is "not sure"
// or "get a human interpreter". Never guess.

const CATEGORY_LABEL = { health: "health", legal: "a legal matter", emergency: "an emergency" };

export function describeResult(r) {
  switch (r?.status) {
    case "match":
      return { tone: "ok", title: r.english, body: "", speak: r.english };
    case "interpreter_needed": {
      const about = CATEGORY_LABEL[r.category] ?? "something important";
      const body =
        r.category === "emergency"
          ? "If someone is in danger, call 911 now."
          : "Please get a human interpreter. This app is not sure enough.";
      return { tone: "alert", title: `This may be about ${about}.`, body, speak: null };
    }
    case "unsure":
      return { tone: "warn", title: "Not sure.", body: "Please try again, or ask for a human interpreter.", speak: null };
    case "no_phrases":
      return { tone: "warn", title: "No phrases taught yet.", body: "A helper needs to teach phrases on the Teach tab first.", speak: null };
    case "too_short":
    case "too_quiet":
    case "too_loud":
      return { tone: "warn", title: "Please try again.", body: r.message ?? QUALITY[r.status], speak: null };
    default:
      return { tone: "warn", title: "Something went wrong.", body: "Please try again, or ask for a human interpreter.", speak: null };
  }
}

export const QUALITY = {
  too_short: "The recording is too short. Please say the whole phrase.",
  too_quiet: "The recording is too quiet. Please move closer to the microphone.",
  too_loud: "The recording is too loud. Please move a little away from the microphone.",
};
