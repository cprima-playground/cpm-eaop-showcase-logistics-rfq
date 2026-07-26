# Test deck

These are small Reveal.js test decks for the logistics showcase story:

- `index.html` — compact showcase overview
- `agentically-enhanced-job.html` — the Transport Planner onboarding story

From the repository root, serve the `web` directory with any static HTTP server,
then open `/slides/`:

```powershell
python -m http.server 8000 --directory web
```

Open <http://localhost:8000/slides/> for the overview or
<http://localhost:8000/slides/agentically-enhanced-job.html> for the job story.
Reveal.js is loaded from its public CDN, so an internet connection is required
for the presentation runtime. In the job-story deck, use the left/right arrows
for major chapters and the up/down arrows to reveal the supporting story within
each chapter.
