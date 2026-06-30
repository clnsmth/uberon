# Setup and Verification Guide for `@ontology-agent`

This guide outlines the manual configuration steps and tests required to transition the Uberon fork's agentic workflows to Google Gemini and run under a secure, dedicated **GitHub App** named `@ontology-agent` (or `@ontology-agent-edi`).

---

## 1. Manual Configuration Steps

Using a GitHub App is the industry best practice because it automatically generates short-lived, secure access tokens on-the-fly and eliminates the need for managing a static personal access token (PAT).

### Step A: Create and Configure Your GitHub App

1. **Navigate to App Creation:**
   * Go to your personal GitHub settings (or Organization settings) and select **Developer Settings > GitHub Apps > New GitHub App**.
2. **App Details:**
   * **GitHub App name:** Enter `ontology-agent` (or `ontology-agent-edi` if the name is already taken on GitHub).
   * **Homepage URL:** Enter your repository fork's URL.
   * **Webhook:** Uncheck **Active** (the workflow is event-triggered, so a direct webhook listener is not needed).
3. **Repository Permissions:**
   * Under **Permissions > Repository permissions**, configure the following:
     * **Contents:** Read & Write (to commit and push files)
     * **Issues:** Read & Write (to view and comment on issues)
     * **Pull requests:** Read & Write (to create and comment on pull requests)
4. **Create the App:** Click **Create GitHub App**.

### Step B: Download Private Key & Install App

1. **Generate a Private Key:**
   * On your App's settings page, scroll down to **Private keys** and click **Generate a private key**.
   * A `.pem` file will automatically download to your computer. Keep this file secure.
2. **Retrieve App ID:**
   * Note the **App ID** shown at the top of your App's settings page (a multi-digit number).
3. **Install the App:**
   * In the left sidebar of your App's settings page, click **Install App**.
   * Click **Install** next to your personal account (or organization) and select **Only select repositories** to scope it specifically to your Uberon fork.

### Step C: Configure Repository Secrets

In your fork repository on GitHub, navigate to **Settings > Secrets and variables > Actions** and add the following **Repository Secrets**:

1. `GEMINI_API_KEY`: Your Google Gemini API Key.
2. `APP_ID`: The numeric App ID retrieved in **Step B**.
3. `APP_PRIVATE_KEY`: The entire contents of the `.pem` private key file downloaded in **Step B** (including the `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----` lines).

---

## 2. Verification & Testing Plan

Once the configuration steps are complete, execute these three manual test cases to verify functionality.

### Test Case 1: Manual Workflow Dispatch (Smoke Test)
This tests the connection between the GitHub App, token generation, and the Gemini API without needing to parse issue comments.

1. Navigate to the **Actions** tab of your repository on GitHub.
2. Select the **AI Agent GitHub Mentions** workflow from the left sidebar.
3. Click the **Run workflow** dropdown on the right:
   * **Use workflow from:** Choose `main` or your default branch.
   * **Issue or PR number to respond to:** Enter any open issue number (e.g., `1`).
   * **Type of item:** Select `issue`.
   * **The request/prompt for the agent:** Enter `quick question: hello! Are you online?`
4. Click **Run workflow**.
5. **Expected Outcome:**
   * The workflow starts and is named after your run.
   * The agent posts a comment on the specified issue with a status update, answers the question, and appends the standard `@ontology-agent` signature block.

---

### Test Case 2: Triggering via Issue Comment Mention
This verifies that the GitHub comment listener parses the custom `@ontology-agent please` trigger correctly. Since it's a GitHub App, it also matches if you type `@ontology-agent[bot] please`.

1. Open or create a test issue on your repository.
2. Post a comment on the issue with the trigger phrase:
   ```markdown
   @ontology-agent please quick question: what is the active git branch name?
   ```
   *(We include `quick question` here to bypass the heavy ODK container load and get a fast response).*
3. **Expected Outcome:**
   * Within a minute, the workflow is triggered on GitHub Actions.
   * The agent reacts to your comment with a 👀 (`eyes`) reaction.
   * The agent comments back: `🤖 Working on it... Follow along: [View workflow run](url)`.
   * When complete, the agent replies with the command output and signature block.

---

### Test Case 3: Complete Ontology Branch & PR Creation
This tests the full agent capability, including checking out terms, verifying them, pushing, and creating a PR.

1. Open an issue on your repository to edit/create a term. For example:
   > Title: Edit term UBERON:0001742
   > Body: @ontology-agent please update the definition of epiglottic cartilage to match the text in GEMINI.md.
2. **Expected Outcome:**
   * The agent reacts with 👀 and posts a `Working on it...` message.
   * The workflow runs in the ODK container (`obolibrary/odkfull`).
   * The agent:
     1. Creates a new branch named `ontology-agent-issue-<number>-run1`.
     2. Checks out the term via `obo-checkout.pl`.
     3. Makes the requested modifications.
     4. Checks the term back in via `obo-checkin.pl`.
     5. Reserializes the edit file using `robot convert`.
     6. Commits and signs off with `@ontology-agent`.
     7. Pushes the branch and creates a Pull Request targeting your fork using `gh pr create --repo <owner/repo>`.
   * The agent leaves a comment on the original issue referencing the new PR.

---

## 3. Troubleshooting Quick Reference

| Symptom | Probable Cause | Action |
| :--- | :--- | :--- |
| **Workflow doesn't trigger on comments** | Trigger format error, unauthorized user, or workflow not on default branch. | Verify you are posting as `clnsmth` (or a username in `ai-controllers.json`) and using `@ontology-agent please` or `@ontology-agent[bot] please`. Ensure `ai-agent.yml` is merged into the default branch. |
| **Eyes reaction added but agent doesn't reply** | `APP_PRIVATE_KEY` or `APP_ID` is incorrect or the App doesn't have sufficient repository permissions. | Verify the app permissions are set to Write for Contents, Issues, and Pull Requests on your App configuration page. Check repository secrets. |
| **Workflow fails on "Generate token" step** | Incorrect App ID or malformed Private Key. | Verify `APP_ID` is set to the correct numeric App ID and `APP_PRIVATE_KEY` contains the full block of the PEM key, starting with `-----BEGIN RSA PRIVATE KEY-----`. |
| **Workflow fails on "Run Gemini CLI" step** | Missing or incorrect `GEMINI_API_KEY`. | Check repository secrets and verify the API key is active. |
