# Testing with your voice

A step-by-step guide to measuring how well the matcher works for **your** voice, and then for a
**new** voice. It takes about 30–40 minutes.

> **Privacy.** Recordings are private voice data. They are stored in `RVB_DATA_DIR`
> (on macOS: `~/Library/Application Support/RohingyaVoiceInterpreter`), never in git, never
> uploaded. When you download the .zip, unzip it **outside** any cloud-synced folder
> (not on an iCloud Desktop / Documents, OneDrive or Dropbox folder). Delete it when you are done.

## 0. Start the app

```bash
make run          # or: cd backend && ../.venv/bin/python -m uvicorn app.main:factory --factory --reload --port 8000
```

Open **http://localhost:8000** (use `localhost`, not an IP address, or the microphone is blocked).
Go to **Teach**, paste `RVB_ADMIN_TOKEN` from `.env`, and press **Unlock**.

Tips for every recording:
- Quiet room, same microphone throughout, about 20–30 cm from your mouth.
- Press **Record**, wait half a second, say the phrase once, wait half a second, press **Stop**.
- Speak naturally. Small differences between takes are good; they make the test realistic.

---

## Step 1: English sanity check (5 minutes)

This checks the microphone and the pipeline with a language the app's English labels match.

1. On **Teach**, set **Speaker label** to `en-check`.
2. Pick 4 phrases, e.g. *Hello.*, *Thank you.*, *I need water.*, *Where is the washroom?*
3. For each, press **● Record take** and **say the English phrase**. Do **3 takes** each (3 dots fill in).
4. Go to **Speak**, tap the microphone and say one of the 4 phrases. You should see and hear it in English.
5. Say something you did **not** teach (e.g. "The bus is late"). You should get **Not sure**.

If step 4 fails often: check the microphone level (System Settings → Sound → Input), move closer,
and re-record takes that the app flagged as too quiet.

## Step 2: Delete the English recordings

They would confuse the real test. On **Phrases & tests** → **Delete all by speaker**, type
`en-check` → **Delete** → confirm. The takes list should no longer show `en-check`.

---

## Step 3: The real Rohingya test (20 minutes)

### 3a. Teach: 8–10 phrases × 3 takes
1. On **Teach**, set **Speaker label** to `me`.
2. Choose **8–10 phrases** you can say naturally in Rohingya. Include at least **2 sensitive**
   ones (health / legal / emergency) so the safety gate is tested.
3. For each, read the English and **say it in Rohingya**. **3 takes** each.

The app never asks you to write Rohingya: the English label is just the meaning.

### 3b. Fresh test takes
On **Phrases & tests** → **Record a test take**:
1. **Speaker** `me`.
2. For each taught phrase, record **2 test takes** (choose the phrase in the list, then record).
   Do this a few minutes after teaching, so they are truly fresh takes.

Test takes do not teach the app. They are only used to measure accuracy.

### 3c. Phrases you never taught
Still on **Phrases & tests**:
1. Choose **A phrase I never taught**.
2. Optionally type what you said **in English** (e.g. "Where is the bus stop?").
3. Record **3–5** different Rohingya sentences that you did not teach.

The correct answer for these is always **Not sure**.

### 3d. Export and evaluate
1. **⬇ Download .zip** (`rvb-recordings.zip`).
2. Unzip it into a private folder and run the evaluation:

```bash
mkdir -p ~/rvb-eval && unzip -o ~/Downloads/rvb-recordings.zip -d ~/rvb-eval
.venv/bin/python -m rvb_ai.eval_matcher ~/rvb-eval/recordings --test-speakers me
```

---

## Step 4: A second speaker (the new-voice test, 10 minutes)

Ask a second Rohingya speaker to help. They **do not teach**; they only record **test takes**,
so we learn how well your taught templates work for someone else's voice.

1. On **Phrases & tests**, set **Speaker** to `friend` (or any label; no real names needed).
2. For each phrase you taught, they record **2 test takes**.
3. Add **2–3 never-taught** sentences from them too.
4. Export again and run:

```bash
rm -rf ~/rvb-eval/recordings && unzip -o ~/Downloads/rvb-recordings.zip -d ~/rvb-eval
.venv/bin/python -m rvb_ai.eval_matcher ~/rvb-eval/recordings --teach-speakers me --test-speakers friend
```

Expect lower numbers than for your own voice. What matters most is that **wrong-and-shown stays at 0**.

---

## Reading the results

| Line | Plain meaning | What you want |
|---|---|---|
| **Top-1 accuracy** | How often the *closest* phrase was the right one, before any safety rules | High (80 %+ for your own voice is a good MVP) |
| **Shown and correct** | How often the app actually showed the right English | As high as possible, but never at the cost of the next line |
| **WRONG and shown** | How often the app showed English that was **wrong** (including for never-taught phrases) | **0 %** |
| **Sensitive phrases shown wrongly** | Wrong health / legal / emergency answers | **Must be 0** |
| **Confusions** | Pairs of phrases the matcher mixes up | Re-record them or teach more takes; avoid similar-sounding phrases |
| **Per take** | Distance (lower = more similar) and margin (gap to the next phrase) | Correct takes have low distance and a clear margin |
| **Evidence** | Distances for correct vs. wrong / never-taught takes | A clear gap between the two groups |
| **Suggestion** | Thresholds that would give 0 wrong answers with the most correct answers on **your** data | **Not applied** automatically. Decide only after looking at the evidence |

If the suggestion says **WARNING: this would loosen the sensitive-phrase gate**, it needs more
data and a human decision. "Not sure" is always better than a wrong answer.

## Cleaning up

```bash
rm -rf ~/rvb-eval ~/Downloads/rvb-recordings.zip
```

In the app, **Delete all by speaker** removes a speaker's recordings from `RVB_DATA_DIR`.
