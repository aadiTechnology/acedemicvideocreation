# Academic Video Creation: user guide

How to use the application from first sign-in to an approved lesson. Each part has a matching video (see the end). Screens are from the running application; the orange boxes and numbers show where to click.

You can follow along with the sample files in `sample/` (`lesson.csv`, `lesson_plan.json`, and `lesson_with_errors.csv` for seeing validation errors).

## 0. Sign in and roles

Open the Academic Video Creation address. You are taken to the Aadi sign-in page. Sign in with your Aadi email and password; it is the same account as your other Aadi products.

![Sign in](img/30-signin.png)

If you see "Product not available", your company has no Academic Video Creation subscription or you are not a member: ask your Aadi administrator.

| Role | Can do |
|---|---|
| Admin | Everything; gives roles to people. The first person of a company to sign in becomes its admin |
| Content operator | Create lessons, import content, send for review |
| Reviewer | Approve, request changes, reject |
| Production operator | Generate videos |
| No role | Read only |

You only see your own company's data.

## 1. Set up classes, subjects, chapters and topics

You do this once; every lesson reuses it.

1. On the Lessons page click **Structure**.

   ![Home](img/01-home.png)

2. Type the class name (for example `Class 7`) and click **Add**.

   ![Structure](img/02-structure.png)

3. Under **Subjects, chapters, topics**: choose the class, type the subject, click **Add subject**.

   ![Subject](img/04-subject.png)

4. Choose the subject, enter the chapter number and title, click **Add chapter**.

   ![Chapter](img/05-chapter.png)

5. Choose the chapter, type the topic, click **Add topic**.

   ![Topic](img/06-topic.png)

A class, subject, chapter or topic can be removed only when nothing is below it.

## 2. Create a lesson

1. Click **Lessons**. In **New lesson** choose the class, subject, chapter and topic.

   ![Where](img/07-lesson-where.png)

2. Enter (1) the title, (2) the target length in minutes, tick (3) the languages, add the learning objectives (one per line), then click (4) **Create lesson**.

   ![Details](img/08-lesson-details.png)

3. The lesson appears in the list with one chip per language. Every language starts as **draft**.

   ![Created](img/09-lesson-created.png)

4. Click the lesson row to open it, then click a language version to work on it. You can add a missing language later from the same place.

   ![Open](img/10-lesson-open.png)

## 3. Get the content (ChatGPT, done by you)

Open a language version and click **Show ChatGPT prompt**. The prompt is built from your lesson (class, subject, topic, language, length). Copy it into ChatGPT yourself and save the two files it returns as `lesson.csv` and `lesson_plan.json`. The application never contacts ChatGPT.

![Prompt](img/12-prompt.png)

## 4. Import and check

1. Choose a ZIP, or `lesson.csv` together with `lesson_plan.json`. Click **Check only** to test without saving, then **Import**.

   ![Choose files](img/14-choose-files.png)

2. If something is wrong, the problems are listed in plain words, with the row number, and **nothing is imported**. Fix the file and try again.

   ![Errors](img/13-import-errors.png)

3. When the check passes you see the slide count and the estimated narration time. A note appears if it is far from your target length.

   ![Check ok](img/15-check-ok.png)

Rules for `lesson.csv`: UTF-8; exactly the columns `Slide, Module, voice_text, subtitle_text, visual_instruction`; Slide numbers are whole numbers starting at 1 with no repeats; no empty cells. In a ZIP, only `lesson.csv`, `lesson_plan.json`, `academic_review.json` and PNG/JPEG pictures in `assets/` are accepted.

## 5. Review and approve

1. Read the imported content: objectives, then the narration, subtitle and visual instruction of every slide.

   ![Imported](img/16-imported.png)

2. Content operator: click **Send for review**.

   ![Send](img/17-send-review.png)

3. Reviewer: add a note and click **Approve**, or **Request changes** / **Reject** (a note is required for these two).

   ![Decision](img/18-decision.png)

4. The status becomes **approved**. Only approved versions can go to video production. Importing new content cancels an approval and the review starts again.

   ![Approved](img/19-approved.png)

5. The history shows every step, with the note and the time.

   ![History](img/20-history.png)

## 6. Make the video

Production operator, on an **approved** version, in step 5 **Make the video**.

1. Choose the voice, the quality and subtitles, then click **Generate video**. Only one video at a time is made for each language version, and a repeated click never creates a second one.

   ![Options](img/22-video-options.png)

2. **Google Colab voice:** the video waits for narration audio. (1) Download the narration file, (2) open `notebooks/colab_tts.ipynb` in Colab (GPU), upload the file and run it; it produces `narration_audio.zip`, (3) choose that ZIP and click **Upload narration**. A ZIP with missing or extra files is rejected with the reason, and the video keeps waiting.

   ![Waiting for audio](img/23-awaiting-audio.png)

3. The video joins the queue, then a progress bar shows how far along it is. The page updates itself; you can leave and come back.

   ![Queued](img/24-queued.png)
   ![Progress](img/25-progress.png)

4. When the status is **Ready**, the video plays on the page. Click **Download MP4**. The supporting files are listed below it. The file is checked (size and SHA-256) when it is copied from the video service, so a damaged file is never shown as ready.

   ![Ready](img/26-ready.png)

If something fails, the message says what happened. **Try again** is offered when it is safe; **Cancel** stops an unfinished video; **Make the video again** starts a new one after content changes.

## 7. Animated slides

Videos are made with **animated slides** by default (Slides: *Animated (recommended)* in step 5; choose *Plain* for still slides). The headline slides in, the points of each slide appear one by one as the narrator reaches them, the point being spoken is highlighted, and slides fade into each other. Timing follows the narration sentence by sentence (an estimate, not word by word).

A slide can use a layout instead of bullets. The ChatGPT prompt already asks for them, in `lesson_plan.json` under `slides`:

| Layout | Use it for | Example |
|---|---|---|
| `bullets` (default) | short points | `"bullets": ["Sunlight gives energy", "Water from the roots"]` |
| `flow` | a procedure or inputs, process, outputs; 2 to 5 steps, arrows are drawn | `"diagram": {"steps": ["Boil the leaf", "Add iodine", "Blue-black means starch"]}` |
| `equation` | a formula; terms appear in order | `"diagram": {"terms": ["Carbon dioxide", "+", "Water", "→", "Glucose"]}` |
| `cycle` | a loop of 3 to 6 stages, e.g. the water cycle | `"diagram": {"nodes": ["Evaporation", "Condensation", "Precipitation", "Collection"]}` |
| `compare` | two things side by side | `"diagram": {"left": {"title": "A", "points": ["..."]}, "right": {"title": "B", "points": ["..."]}}` |

Keep labels short (1 to 4 words) and list items in the order the narrator says them. If a diagram is not valid, the import check names the slide and the problem. Details: `ScriptToVideo/docs/architecture/ANIMATED_SLIDES.md`.

![Flow](img/anim-flow.png)
![Equation](img/anim-equation.png)
![Cycle](img/anim-cycle.png)
![Compare](img/anim-compare.png)

## 8. Built-in science pictures

For some topics a slide can show **the actual thing being taught** as an animated picture, drawn for you with labels in the lesson language. Its parts appear one by one as the narrator mentions them. Available now:

| Picture (`template`) | Parts, in the order they appear |
|---|---|
| `refraction` | the two media, the normal, the incident ray, the refracted ray, the angle of incidence, the angle of refraction. The angles come from the physics: towards the normal into glass or water, away from it into air |
| `photosynthesis` | sunlight, water from the roots, carbon dioxide, chlorophyll, oxygen, glucose |
| `water_cycle` | the sun heating the sea, evaporation, condensation, precipitation, collection |
| `leaf_section` | upper epidermis, palisade cells, spongy cells, lower epidermis, stomata, chloroplasts |

The ChatGPT prompt already knows them. A slide uses one like this in `lesson_plan.json`:
`{"slide": 3, "headline": "Refraction: air to glass", "layout": "illustration", "diagram": {"template": "refraction", "params": {"medium": "glass", "direction": "into_denser", "angle": 50}}}`

**Write the narration of that slide with one sentence per part, in the order above**, because each part appears when the narrator reaches its sentence. A complete example lesson is in `docs/user-guide/sample/refraction/`. The Hindi and Marathi labels need a subject-expert review.

![Refraction in a finished video](img/illus-refraction-real-video.png)
![Photosynthesis](img/illus-photosynthesis-en-IN.png)
![Water cycle](img/illus-water_cycle-en-IN.png)
![Inside a leaf](img/illus-leaf_section-en-IN.png)

## Videos for each part

| Part | Video |
|---|---|
| Sign in and roles | `docs/demos/sprint-4b-identity.mp4` |
| Set up and create a lesson (sections 1 and 2) | `docs/demos/sprint-4-foundation.mp4` |
| From content to approval (sections 3 to 5) | `docs/demos/sprint-5-import-review.mp4` |
| Make the video (section 6) | `docs/demos/sprint-6-integration.mp4` |
| Animated slides (section 7) | `docs/demos/sprint-9-animated-slides.mp4` |
| Built-in science pictures (section 8) | `docs/demos/sprint-10-illustrations.mp4` |
| **Everything above in one video (about 12 minutes)** | `docs/demos/full-user-guide.mp4` |


## Rebuilding the screens and videos

Start the API (`AUTH_MODE=dev`) and web app on a fresh database, then run `docs/user-guide/capture_guide.py` and `capture_signin.py` (Playwright with Edge). Videos are built with `ScriptToVideo/docs/demos/build_demo.py` from `docs/demos/sprint-*.json`.

## 9. More layouts (new)

Five more slide layouts can be used in `lesson_plan.json` `slides`. The ChatGPT prompt already explains them and tells ChatGPT to choose the one that fits each slide. Hindi and Marathi section headings (Aim, Procedure, Recap and so on) are unreviewed translations.

| Layout | Use it for | Key fields |
|---|---|---|
| `text_illustration` | points on the left, a built-in picture building up on the right | `bullets` (1 to 5), `diagram.template` |
| `timeline` | events in time order | `diagram.events`: 3 to 6 items with `label` (for example a year) and optional `sub` |
| `labelled_diagram` | naming the parts of a simple outline | `diagram.parts`: 2 to 8 items with `label`, `x`, `y` (0 to 1); `shape` oval, rect or circle |
| `experiment` | a real-world activity | `diagram.aim`, `procedure` (1 to 4 steps); optional `materials`, `observation`, `conclusion` |
| `recap` | the closing summary | `bullets` (2 to 5); optional `diagram.question` |

Layout choice: the video engine can recommend layouts (`POST /api/v1/layouts/recommend`: subject, topic, objective, class); the ChatGPT prompt gives the same guidance in words. A person always decides.

## 10. Edit a slide

On the review page, a content operator sees **Edit** at the end of each slide row. The editor has the layout, headline, bullets and diagram (JSON; picking a layout fills an example). **Preview** shows the slide as it will appear in the video; the slider chooses the moment. **Suggest a layout** lists up to three layouts with the reason for each; a click applies one. **Save slide** checks the slide with the import rules: an invalid slide is refused with the reason. Saving changes the content, so an approved version becomes a draft and needs a new review.

If an import says the language in `lesson_plan.json` does not match (for example `'en-IN'` in a Hindi version), each language version needs its own files: use **Show ChatGPT prompt** in that version.

## 11. Captions and narration speed

- Captions are larger (54 px) with at most two lines. Important words listed in `key_terms` (in `lesson_plan.json`, or per slide in the slide editor) are highlighted in gold while they are on screen. The ChatGPT prompt asks for `key_terms`.
- In **Make the video**, **Narration speed** is slow, normal or fast. Quality now defaults to 480p and the voice to Azure.

The slide editor can also change a slide's **module, narration, caption text and visual note**. Use "Make the caption text the same as the narration" to fix the short-captions warning. Saving rewrites `lesson.csv` with every field quoted, so the file stays valid. Narration and caption text cannot be left empty. Tick "Show captions in the preview" to see the caption as it will appear.

## 12. Technical courses and the code layout

**Courses next to classes.** In **Structure**, choose the **Type** when you add the top-level item: *School* (class, subject, chapter, topic) or *Technical course* (course, track, module, lesson topic). The labels in the forms follow the type. Existing classes are School. The ChatGPT prompt changes with the type: a technical course asks for learner level, complete runnable code and exact output.

**The code layout** (`"layout": "code"`) shows code in an editor, highlights the lines being explained as the narrator reaches them, and can show an **Output** console and a **Variables** table:

    {"layout": "code", "diagram": {"language": "python", "code": "x = 5\nprint(x)",
      "steps": [{"lines": [1], "vars": {"x": "5"}}, {"lines": [2], "output": "5"}]}}

- Write **one narrated sentence per step**, in the order of the steps.
- Up to 18 lines of up to 80 characters and 12 steps; languages: python, javascript, java, c, cpp, sql, bash, html, json.
- **The code is not run.** The output and variable values are what the author writes, so check them in **Edit slide > Preview** before approving.
- A complete sample lesson is in `docs/user-guide/sample/python/` (lesson.csv and lesson_plan.json, 5 slides).

## 13. Quality check

When an animated video is ready, a **Quality check** appears under it: a result (passed, passed with points to review, problems found), a score out of 100, a score for each area, and the problems found with the slide number and what to fix. It is checked automatically before the video is made and again on the finished video.

- **Errors** in captions or narration (for example captions that overlap, or missing audio) stop the video from being made, and the message names the slide.
- **Warnings** do not stop anything: text close to the frame edge, a label the narrator never says, labels in a different order from the narration, a length far from the lesson's target, an objective that may not be covered.
- The score is a rule-based estimate, not a judgement of the lesson. The panel lists what a person still has to check: correctness of the content, Hindi and Marathi wording and voice, and any built-in pictures.

## 14. People, departments and roles

The **People and roles** tab (for people with permission to see it) manages who can do what in this product. It comes from the shared organisation kit (`aadi-org-kit`), so it works the same way in every Aadi product; each product has its own people, departments and roles.

- **Accounts.** Identity decides whether a person may enter the product (their company has it and they are an active member). The product then needs an account for them. The first person of a company to sign in becomes its administrator; everyone else must be added under **People** (email, name, title, department, role). They show as *invited* and are linked when they first sign in. Someone who signs in without an account sees "No account in this product yet".
- **Departments** can be nested; a department with people or sub-departments cannot be deleted.
- **Roles and features** is a table of what each role may do. Built-in roles: Administrator, Content operator, Reviewer, Production operator and Viewer (read only). Administrators can add roles and tick features; every company has its own roles. A person has one role.
- **Protection.** The last active administrator cannot be suspended or demoted. Suspending a person refuses them at once, even with a session open. A person in one company never sees another company's people.
- **Activity** lists every change with who made it.
- People who had roles before this change were moved across with the equal role (several roles became a combined role), so nobody lost or gained access.
- The older `/api/admin/users` endpoints are replaced by `/api/org/...`.
