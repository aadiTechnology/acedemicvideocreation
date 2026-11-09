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

## Videos for each part

| Part | Video |
|---|---|
| Sign in and roles | `docs/demos/sprint-4b-identity.mp4` |
| Set up and create a lesson (sections 1 and 2) | `docs/demos/sprint-4-foundation.mp4` |
| From content to approval (sections 3 to 5) | `docs/demos/sprint-5-import-review.mp4` |
| Make the video (section 6) | `docs/demos/sprint-6-integration.mp4` |
| **Everything above in one video (7.5 minutes)** | `docs/demos/full-user-guide.mp4` |


## Rebuilding the screens and videos

Start the API (`AUTH_MODE=dev`) and web app on a fresh database, then run `docs/user-guide/capture_guide.py` and `capture_signin.py` (Playwright with Edge). Videos are built with `ScriptToVideo/docs/demos/build_demo.py` from `docs/demos/sprint-*.json`.
